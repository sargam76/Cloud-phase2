import json
import os
import bcrypt
import jwt
import secrets
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

import azure.functions as func
from azure.storage.blob import BlobServiceClient
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

from lambda_function import process_nutritional_data_from_azurite, build_recipes_list

app = func.FunctionApp()

CONN_STR = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
RESULTS_CONTAINER = "results"
INSIGHTS_BLOB = "nutritional_insights.json"
RECIPES_BLOB = "recipes.json"
USERS_TABLE = "Users"
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")


def bsc():
    return BlobServiceClient.from_connection_string(CONN_STR)


def users_table():
    tsc = TableServiceClient.from_connection_string(CONN_STR)
    try:
        tsc.create_table(USERS_TABLE)
    except ResourceExistsError:
        pass
    return tsc.get_table_client(USERS_TABLE)


def json_response(payload, status=200):
    return func.HttpResponse(json.dumps(payload, default=str), status_code=status,
                              mimetype="application/json",
                              headers={"Access-Control-Allow-Origin": "*"})


@app.function_name(name="process_diet_data")
@app.blob_trigger(arg_name="blob", path="datasets/All_Diets.csv", connection="AzureWebJobsStorage")
def process_diet_data(blob: func.InputStream):
    result, df = process_nutritional_data_from_azurite()
    recipes = build_recipes_list(df)

    client = bsc()
    try:
        client.create_container(RESULTS_CONTAINER)
    except ResourceExistsError:
        pass
    client.get_blob_client(RESULTS_CONTAINER, INSIGHTS_BLOB).upload_blob(json.dumps(result, default=str), overwrite=True)
    client.get_blob_client(RESULTS_CONTAINER, RECIPES_BLOB).upload_blob(json.dumps(recipes, default=str), overwrite=True)
    print(f"Cache rebuilt: {result['metadata']}")


@app.route(route="nutritional-insights", auth_level=func.AuthLevel.ANONYMOUS)
def nutritional_insights(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = bsc().get_blob_client(RESULTS_CONTAINER, INSIGHTS_BLOB).download_blob().readall()
    except ResourceNotFoundError:
        return json_response({"error": "No cache yet"}, 404)
    return func.HttpResponse(data, mimetype="application/json",
                              headers={"Access-Control-Allow-Origin": "*"})


@app.route(route="recipes", auth_level=func.AuthLevel.ANONYMOUS)
def recipes(req: func.HttpRequest) -> func.HttpResponse:
    try:
        raw = bsc().get_blob_client(RESULTS_CONTAINER, RECIPES_BLOB).download_blob().readall()
    except ResourceNotFoundError:
        return json_response({"error": "No cache yet"}, 404)
    all_recipes = json.loads(raw)

    diet_type = (req.params.get("diet_type") or "").lower()
    search = (req.params.get("search") or "").lower()
    page = max(1, int(req.params.get("page", 1)))
    page_size = min(100, max(1, int(req.params.get("page_size", 10))))

    filtered = all_recipes
    if diet_type and diet_type != "all":
        filtered = [r for r in filtered if r["Diet_type"].lower() == diet_type]
    if search:
        filtered = [r for r in filtered if search in r["Recipe_name"].lower() or search in r["Cuisine_type"].lower()]

    total = len(filtered)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    start = (page - 1) * page_size

    return json_response({
        "results": filtered[start:start + page_size],
        "page": page, "total_pages": total_pages, "total_results": total,
    })


def issue_jwt(email, name, provider):
    payload = {"sub": email, "name": name, "provider": provider,
               "exp": datetime.now(timezone.utc) + timedelta(hours=24)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@app.route(route="auth/register", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def auth_register(req: func.HttpRequest) -> func.HttpResponse:
    body = req.get_json()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    name = (body.get("name") or email.split("@")[0]).strip()
    if not email or len(password) < 8:
        return json_response({"error": "Valid email + password (min 8 chars) required"}, 400)

    table = users_table()
    try:
        table.get_entity(partition_key="user", row_key=email)
        return json_response({"error": "Account already exists"}, 409)
    except ResourceNotFoundError:
        pass

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    table.create_entity({"PartitionKey": "user", "RowKey": email, "email": email,
                          "display_name": name, "password_hash": pw_hash, "provider": "password"})
    return json_response({"token": issue_jwt(email, name, "password"), "name": name, "email": email}, 201)


@app.route(route="auth/login", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def auth_login(req: func.HttpRequest) -> func.HttpResponse:
    body = req.get_json()
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    try:
        entity = users_table().get_entity(partition_key="user", row_key=email)
    except ResourceNotFoundError:
        return json_response({"error": "Invalid email or password"}, 401)

    if entity.get("provider") != "password" or not bcrypt.checkpw(password.encode(), entity["password_hash"].encode()):
        return json_response({"error": "Invalid email or password"}, 401)

    return json_response({"token": issue_jwt(email, entity["display_name"], "password"),
                           "name": entity["display_name"], "email": email})


@app.route(route="auth/me", auth_level=func.AuthLevel.ANONYMOUS)
def auth_me(req: func.HttpRequest) -> func.HttpResponse:
    token = (req.headers.get("Authorization") or "").replace("Bearer ", "")
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return json_response({"error": "Not authenticated"}, 401)
    return json_response({"email": claims["sub"], "name": claims["name"]})


GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET")
GITHUB_CALLBACK = os.environ.get("GITHUB_OAUTH_CALLBACK_URL")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "")


@app.route(route="auth/oauth/github/start", auth_level=func.AuthLevel.ANONYMOUS)
def oauth_github_start(req: func.HttpRequest) -> func.HttpResponse:
    params = {"client_id": GITHUB_CLIENT_ID, "redirect_uri": GITHUB_CALLBACK,
              "scope": "read:user user:email", "state": secrets.token_urlsafe(16)}
    url = "https://github.com/login/oauth/authorize?" + urllib.parse.urlencode(params)
    return func.HttpResponse(status_code=302, headers={"Location": url})


@app.route(route="auth/oauth/github/callback", auth_level=func.AuthLevel.ANONYMOUS)
def oauth_github_callback(req: func.HttpRequest) -> func.HttpResponse:
    code = req.params.get("code")
    token_req = urllib.request.Request(
        "https://github.com/login/oauth/access_token",
        data=urllib.parse.urlencode({"client_id": GITHUB_CLIENT_ID, "client_secret": GITHUB_CLIENT_SECRET,
                                      "code": code, "redirect_uri": GITHUB_CALLBACK}).encode(),
        headers={"Accept": "application/json"})
    with urllib.request.urlopen(token_req) as r:
        access_token = json.loads(r.read())["access_token"]

    user_req = urllib.request.Request("https://api.github.com/user",
                                       headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(user_req) as r:
        gh_user = json.loads(r.read())

    email = gh_user.get("email") or f"{gh_user['login']}@users.noreply.github.com"
    name = gh_user.get("name") or gh_user["login"]

    table = users_table()
    try:
        table.get_entity(partition_key="user", row_key=email)
    except ResourceNotFoundError:
        table.create_entity({"PartitionKey": "user", "RowKey": email, "email": email,
                              "display_name": name, "provider": "github"})

    token = issue_jwt(email, name, "github")
    return func.HttpResponse(status_code=302, headers={"Location": f"{FRONTEND_URL}/dashboard.html#token={token}"})
