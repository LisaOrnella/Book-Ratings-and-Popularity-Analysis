import os, boto3, psycopg2
from dotenv import load_dotenv
load_dotenv()

# Test Postgres
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT 1;')
print('Postgres OK:', cur.fetchone())
conn.close()

# Test S3
s3 = boto3.client('s3', region_name=os.environ['AWS_REGION'])
s3.put_object(Bucket=os.environ['S3_BUCKET'], Key='test.txt', Body=b'hello')
print('S3 OK: uploaded test.txt')