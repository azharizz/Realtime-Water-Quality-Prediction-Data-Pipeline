
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import StructType, StructField, StringType, DoubleType
from pyspark.sql.functions import from_json
from google.cloud import storage

from pyspark.ml import Pipeline
from pyspark.ml.classification import RandomForestClassifier
from pyspark.ml.feature import VectorAssembler
from pyspark.ml.evaluation import MulticlassClassificationEvaluator
from pyspark.sql.functions import isnan, when, count, col
from pyspark.sql.functions import rand
from pyspark.sql.functions import count
from pyspark.ml.feature import StandardScaler
from pyspark.sql.functions import current_timestamp

from pyspark.sql import SparkSession

import os 

print(f"OS NOW ====================== {os.getcwd()}")

print('LIST DIR')

print(os.listdir())



spark = SparkSession.builder \
    .appName("WaterPySparkApp") \
    .config("spark.jars.packages", "org.apache.hadoop:hadoop-cloud-storage:3.3.1") \
    .config("spark.hadoop.fs.AbstractFileSystem.gs.impl", "com.google.cloud.hadoop.fs.gcs.GoogleHadoopFileSystem") \
    .config("spark.jars", "/app/gcs-connector-hadoop3-latest.jar,/app/spark-3.1-bigquery-0.30.0.jar,/app/util-2.2.12-javadoc.jar") \
    .getOrCreate()

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/app/key_file.json"


print("Initialize model")
print("==================================================================================================================================================")

def initialize_model():
    df = spark.read.csv('water_potability.csv', header=True, inferSchema=True)

    df = df.na.drop()

    feature_cols = df.columns
    feature_cols.remove('Potability')

    assembler = VectorAssembler(inputCols=feature_cols, outputCol='features')
    df_transformed  = assembler.transform(df)

    # Calculate the maximum count for any label value
    max_count = df_transformed.groupBy('Potability').count().agg({'count': 'max'}).collect()[0][0]

    # Replicate the minority class rows to achieve the maximum count label distribution
    class_counts = df_transformed.groupBy('Potability').count().collect()
    oversampled_data = None
    for row in class_counts:
        label = row['Potability']
        count = row['count']
        if count == max_count:
            # No oversampling needed for this label
            continue
        oversampling_factor = max_count // count
        oversampled_label_data = df_transformed.filter(f'Potability = {label}').repartition(oversampling_factor)
        oversampled_label_data = oversampled_label_data\
            .orderBy(rand())\
            .limit(max_count - count)
        if oversampled_data is None:
            oversampled_data = oversampled_label_data
        else:
            oversampled_data = oversampled_data.union(oversampled_label_data)

    # Combine the original data with the oversampled data
    resampled_df = df_transformed.union(oversampled_data)

    # Select the 'features' and 'label' columns
    resampled_df = resampled_df.select(['features', 'Potability'])

    assembler = VectorAssembler(inputCols=feature_cols, outputCol='features',handleInvalid="skip" )
    scaler = StandardScaler(inputCol="features", outputCol="scaled_features")
    rf = RandomForestClassifier(featuresCol="scaled_features", labelCol="Potability")
    pipeline = Pipeline(stages=[assembler, scaler, rf])

    model = pipeline.fit(df)

    predictions = model.transform(df)
    evaluator = MulticlassClassificationEvaluator(labelCol='Potability', predictionCol='prediction', metricName='accuracy')
    accuracy = evaluator.evaluate(predictions)
    print('Accuracy = {:.2f}%'.format(accuracy * 100))

    return model


model = initialize_model()


print("Finish model")
print("==================================================================================================================================================")



client = storage.Client()

spark.conf.set("spark.sql.repl.eagerEval.enabled", True)


print("Trying to get read stream")
print("==================================================================================================================================================")

kafka_topic = "waterdb.water_quality_collection"

print(f"OS NOW ====================== {os.getcwd()}")

print('LIST DIR')

print(os.listdir())



df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "broker:29092") \
    .option("startingOffsets", "earliest") \
    .option("subscribe", kafka_topic) \
    .load()

print("Transform schema, payload")
print("==================================================================================================================================================")


schema = StructType([
    StructField("schema", StringType(), nullable=False),
    StructField("payload", StringType(), nullable=False)
])


df = df.selectExpr("CAST(value AS STRING)")

parsed_df = df.select(from_json(df.value, schema).alias("parsed_data")).select("parsed_data.*")


print("Transform fullDocument")
print("==================================================================================================================================================")



schema = StructType([
    StructField("_id", StringType(), nullable=False),
    StructField("operationType", StringType(), nullable=True),
    StructField("clusterTime", StringType(), nullable=True),
    StructField("wallTime", StringType(), nullable=True),
    StructField("fullDocument", StringType(), nullable=True),
    StructField("ns", StringType(), nullable=True),
    StructField("documentKey", StringType(), nullable=True)
])



df = parsed_df.selectExpr("CAST(payload AS STRING)")

df = df.select(from_json(df.payload, schema).alias("data")).select("data.*")



print("Transform every column ph,")
print("==================================================================================================================================================")



schema = StructType([
    StructField("ph", DoubleType(), nullable=True),
    StructField("Hardness", DoubleType(), nullable=True),
    StructField("Solids", DoubleType(), nullable=True),
    StructField("Chloramines", DoubleType(), nullable=True),
    StructField("Sulfate", DoubleType(), nullable=True),
    StructField("Conductivity", DoubleType(), nullable=True),
    StructField("Organic_carbon", DoubleType(), nullable=True),
    StructField("Trihalomethanes", DoubleType(), nullable=True),
    StructField("Turbidity", DoubleType(), nullable=True)
])

df = df.selectExpr("CAST(fullDocument AS STRING)")

df = df.select(from_json(df.fullDocument, schema).alias("data")).select("data.*")


print("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")

# Perform necessary transformations on the DataFrame

print("Trying to write stream")
print("================================================================================================")


temp_output_path = "testing.csv"


output_path = "testing.csv"


df.printSchema()


def write_to_gcs(df, epoch_id):

    local_output_path = "output.csv"
    gs_output_path = "checkpoint"

    print("MODEL PREDICT")
    print("================================================================================================")

    print(type(model))

    prediction = model.transform(df)

    df.printSchema()
    prediction.printSchema()

    prediction = prediction.select("ph", "Hardness", "Solids", "Chloramines", "Sulfate", "Conductivity", "Organic_carbon", "Trihalomethanes", "Turbidity", "prediction", current_timestamp().alias("etl_date"))

    prediction.printSchema()
    prediction.show(5)

    prediction.write \
        .format("csv") \
        .option("header", "true") \
        .mode("overwrite") \
        .save(local_output_path)


    print(os.listdir())

    bucket = client.get_bucket("water-quality-bucket")
    for file_name in os.listdir(local_output_path):
        file_path = os.path.join(local_output_path, file_name)
        blob = bucket.blob(f"{gs_output_path}/{file_name}")
        blob.upload_from_filename(file_path)



query = df.writeStream \
    .foreachBatch(write_to_gcs) \
    .start()



print("saveSuccess")

print("=======================================================================")
print(os.listdir())
print(os.listdir("/app/"))



query.awaitTermination()


