import json
import azure.functions as func
from lambda_function import main as process_data

app = func.FunctionApp()

@app.route(route="nutritional-insights", auth_level=func.AuthLevel.ANONYMOUS)
def nutritional_insights(req: func.HttpRequest) -> func.HttpResponse:
    result = process_data()
    return func.HttpResponse(
        json.dumps(result),
        mimetype="application/json",
        headers={"Access-Control-Allow-Origin": "*"}
    )
