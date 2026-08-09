import time
import json
import os
import io
import pandas as pd
from azure.storage.blob import BlobServiceClient

def process_nutritional_data_from_azurite():
    start_time = time.time()

    connect_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    blob_service_client = BlobServiceClient.from_connection_string(connect_str)

    container_name = "datasets"
    blob_name = "All_Diets.csv"

    container_client = blob_service_client.get_container_client(container_name)
    blob_client = container_client.get_blob_client(blob_name)
    stream = blob_client.download_blob().readall()

    usecols = ["Diet_type", "Recipe_name", "Cuisine_type", "Protein(g)", "Carbs(g)", "Fat(g)"]
    df = pd.read_csv(io.BytesIO(stream), usecols=usecols)
    print("CSV read from Blob Storage successfully!")

    df["Protein(g)"] = pd.to_numeric(df["Protein(g)"], errors="coerce")
    df["Carbs(g)"] = pd.to_numeric(df["Carbs(g)"], errors="coerce")
    df["Fat(g)"] = pd.to_numeric(df["Fat(g)"], errors="coerce")

    df["Protein(g)"] = df["Protein(g)"].fillna(df["Protein(g)"].mean())
    df["Carbs(g)"] = df["Carbs(g)"].fillna(df["Carbs(g)"].mean())
    df["Fat(g)"] = df["Fat(g)"].fillna(df["Fat(g)"].mean())

    avg_macros = df.groupby("Diet_type")[["Protein(g)", "Carbs(g)", "Fat(g)"]].mean().round(2)
    avg_macros_records = avg_macros.reset_index().to_dict(orient="records")

    top_protein = (
        df.groupby("Diet_type")
        .apply(lambda x: x.nlargest(5, "Protein(g)")[["Recipe_name", "Cuisine_type", "Protein(g)"]])
        .reset_index(drop=True)
    )
    top_protein_records = top_protein.to_dict(orient="records")

    diet_counts = df["Diet_type"].value_counts().reset_index()
    diet_counts.columns = ["Diet_type", "recipe_count"]
    diet_counts_records = diet_counts.to_dict(orient="records")

    execution_time_seconds = round(time.time() - start_time, 3)

    result = {
        "avg_macros": avg_macros_records,
        "top_protein_recipes": top_protein_records,
        "diet_recipe_counts": diet_counts_records,
        "metadata": {
            "execution_time_seconds": execution_time_seconds,
            "total_recipes_processed": len(df),
            "generated_at_utc": pd.Timestamp.utcnow().isoformat(),
        },
    }

    print(f"Results computed! Execution time: {execution_time_seconds}s")
    return result, df


def build_recipes_list(df):
    return df[["Recipe_name", "Diet_type", "Cuisine_type", "Protein(g)", "Carbs(g)", "Fat(g)"]].to_dict(orient="records")


def main(req=None):
    result, _ = process_nutritional_data_from_azurite()
    return result
