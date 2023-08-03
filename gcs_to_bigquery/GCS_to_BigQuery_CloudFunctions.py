from google.cloud import bigquery
from google.cloud import storage
import os

def process_file(event, context):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = './keyfile.json'
    # Extracting the bucket and file information from the event
    bucket_name = event['bucket']
    file_name = event['name']
    file_path, file_name = os.path.split(file_name)  # Separating folder path and file name

    # Checking if the file has a .csv extension
    if file_name.lower().endswith('.csv'):
        # Instantiating BigQuery and Storage clients
        bq_client = bigquery.Client()
        storage_client = storage.Client()
        

        # Setting up BigQuery table and dataset details
        dataset_id = 'water_quality'
        table_id = 'water_quality_prediction_table'

        # Constructing the BigQuery table reference
        table_ref = bq_client.dataset(dataset_id).table(table_id)

        try:
            # Loading the data from Cloud Storage into BigQuery
            job_config = bigquery.LoadJobConfig()
            job_config.source_format = bigquery.SourceFormat.CSV
            job_config.skip_leading_rows = 1  # If CSV file has a header
            job_config.autodetect = True  # Detect schema automatically

            # Constructing the Cloud Storage file URI
            file_uri = f'gs://{bucket_name}/{file_path}/{file_name}'

            # Loading the file into BigQuery
            load_job = bq_client.load_table_from_uri(
                file_uri, table_ref, job_config=job_config
            )
            load_job.result()  # Waits for the job to complete

            # File loaded successfully, delete the file from Cloud Storage
            blob = storage_client.get_bucket(bucket_name).blob(f'{file_path}/{file_name}')
            blob.delete()

            print(f"File {file_name} loaded into BigQuery table {table_id}")
        except Exception as e:
            print(f"Error loading file {file_name} into BigQuery: {str(e)}")
    else:
        # File does not have a .csv extension, delete the file from Cloud Storage
        blob = storage_client.get_bucket(bucket_name).blob(f'{file_path}/{file_name}')
        blob.delete()
        print(f"File {file_name} deleted from Cloud Storage")