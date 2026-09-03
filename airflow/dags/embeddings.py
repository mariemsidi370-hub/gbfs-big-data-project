import os

import openai
import psycopg2
import time

openai.api_key = os.getenv("OPENAI_API_KEY")
print('API key loaded: True')

training_data = [
    {'error': 'AirflowException: Dynamic task mapping exceeded limit', 'solution': 'Check the task count limit in the configuration. Consider increasing the task limit or optimizing task mapping logic.'},
    {'error': 'AirflowException: Task instance not found', 'solution': 'Verify database connection is stable. Check if task instances exist in the metadata database. Consider re-running the DAG.'},
    {'error': 'AirflowException: Task is in ''None'' state', 'solution': 'Ensure the task is correctly configured and the execution context is provided, especially for dynamic tasks or task dependencies.'},
    {'error': 'AirflowWebServerException: Webserver 502 Bad Gateway', 'solution': 'Check the webserver logs for details. Ensure all upstream systems are working. Restart the webserver if necessary.'},
    {'error': 'KeyError: KeyError in Variable retrieval', 'solution': 'Check if the Airflow variable exists. Ensure the correct database is used. Verify the variable is defined in the Airflow UI or through code.'},
    {'error': 'PermissionError: Access denied for SSH hook', 'solution': 'Verify the SSH credentials and network access to the target server. Test the connection using a manual SSH client first.'},
    {'error': 'AirflowXComException: TaskInstance not recognized in XCom', 'solution': 'Check if the XCom data is being pushed correctly. Inspect the DAG code for issues in data push logic. Clear any corrupted XCom entries.'},
    {'error': 'AirflowDatabaseException: Error creating database session', 'solution': 'Check the database connection settings and ensure the database is running. Verify user permissions and the number of concurrent connections allowed.'},
    {'error': 'AirflowException: Failed to upload logs to remote storage', 'solution': 'Check the configuration for the remote storage backend. Ensure the connection credentials are correct and the backend is accessible.'},
    {'error': 'AirflowTaskTimeout: Task execution delayed indefinitely', 'solution': 'Review the task timeout settings in the DAG configuration. Increase the timeout if necessary and check for system performance issues.'},
    {'error': 'AirflowSchedulerException: Scheduler loop error', 'solution': 'Check the scheduler logs for specific error messages. Review recent changes to the Airflow environment or DAGs that could affect scheduler behavior.'},
    {'error': 'AirflowParseException: Broken Dag: syntax error', 'solution': 'Review the DAG file for any syntax errors and correct them. Use a linter or Python syntax checker to identify issues.'},
    {'error': 'AirflowDatabaseException: DagRun state update failed', 'solution': 'Check the database connection and permissions. Review any database constraints or performance issues that could prevent state updates.'},
    {'error': 'AirflowWorkerException: Worker not responding', 'solution': 'Check the worker logs. Verify the worker is running and can connect to the database and broker. Restart the worker if necessary.'},
    {'error': 'AirflowDagPausedException: Dag is paused and not running', 'solution': 'Check the DAG status in the Airflow UI and unpause the DAG if needed. Verify the DAG configuration and dependencies.'},
    {'error': 'SyntaxError: Missing colon after if/for/while/def', 'solution': 'Add a colon (:) at the end of the statement. Example: if condition: or for item in list:'},
    {'error': 'IndentationError: Expected an indented block', 'solution': 'Ensure consistent indentation using 4 spaces. Check that all code inside functions, loops, and conditionals is properly indented.'},
    {'error': 'NameError: name ''variable_name'' is not defined', 'solution': 'Check for typos in variable names. Ensure the variable is defined before use. Python is case-sensitive, so ''name'' and ''Name'' are different.'},
    {'error': 'TypeError: unsupported operand type(s) for +: ''int'' and ''str''', 'solution': 'Convert types explicitly. Use str() to convert integers to strings: str(age) or use f-strings: f''Your age is {age}'''},
    {'error': 'ValueError: invalid literal for int() with base 10: ''abc''', 'solution': 'Validate input before conversion. Use try/except to handle conversion errors. Check that the string contains only numeric characters.'},
    {'error': 'IndexError: list index out of range', 'solution': 'Check the length of the list before accessing an index: if len(list) > index: or use try/except. Remember that valid indices are 0 to len-1.'},
    {'error': 'KeyError: ''key_name'' not found in dictionary', 'solution': 'Use dict.get(''key'') to safely access values. Check if the key exists with ''key'' in dict. Verify the key spelling is correct.'},
    {'error': 'AttributeError: ''type'' object has no attribute ''method_name''', 'solution': 'Check the object type before calling methods. Verify the method name spelling. Use hasattr() to check if the attribute exists: hasattr(obj, ''method'')'},
    {'error': 'ModuleNotFoundError: No module named ''module_name''', 'solution': 'Install the missing module: pip install module_name. Check for typos in the import statement. Verify the module is installed in the correct Python environment.'},
    {'error': 'ZeroDivisionError: division by zero', 'solution': 'Check that the denominator is not zero before division. Add a guard clause: if denominator != 0: or use try/except to handle the error.'},
    {'error': 'FileNotFoundError: No such file or directory: ''file_path''', 'solution': 'Check the file path exists. Use absolute paths or verify the current working directory. Use pathlib.Path to handle paths safely.'},
    {'error': 'JSONDecodeError: Expecting value: line 1 column 1 (char 0)', 'solution': 'Check the JSON format. Ensure the input is valid JSON. Use try/except to handle invalid JSON. Verify the file contains JSON data.'},
    {'error': 'ConnectionError: Failed to establish a new connection', 'solution': 'Check network connectivity. Verify the host and port are correct. Add retry logic with exponential backoff for transient failures.'},
    {'error': 'TimeoutError: Operation timed out', 'solution': 'Increase the timeout value. Add retry logic with backoff. Check if the remote service is responding and the network is stable.'},
    {'error': 'RuntimeError: General error condition', 'solution': 'Check the error message for specific details. Review the code logic. Add more specific exception handling to catch the root cause.'}
]

def connect_database():
    try:
        connection = psycopg2.connect(
            host='localhost',
            database='airflow',
            user='airflow',
            password='airflow',
            port='5433',
        )
        print('Connected to PostgreSQL.')
        return connection
    except psycopg2.Error as error:
        print('Database connection error:', error)
        return None

def get_embedding(text):
    text = text.replace('\n', ' ')
    response = openai.Embedding.create(
        input=text,
        model='text-embedding-3-small',
    )
    return response['data'][0]['embedding']

def populate_training_data(connection):
    cur = connection.cursor()
    for record in training_data:
        error_text = record['error']
        solution_text = record['solution']
        cur.execute('SELECT COUNT(*) FROM store_error WHERE error_text = %s', (error_text,))
        count = cur.fetchone()[0]
        if count == 0:
            embedding = get_embedding(error_text)
            cur.execute('INSERT INTO store_error (error_text, solution_text, embedding) VALUES (%s, %s, %s)', (error_text, solution_text, embedding))
            print(f'Inserted: {error_text[:50]}...')
            time.sleep(0.5)
        else:
            print(f'Skipping duplicate: {error_text[:50]}...')
    connection.commit()
    cur.close()
    print(f'Done! Processed {len(training_data)} records.')

def main():
    connection = connect_database()
    if connection is None:
        return
    try:
        populate_training_data(connection)
    except Exception as error:
        connection.rollback()
        print('Error:', error)
    finally:
        connection.close()
        print('Database connection closed.')

if __name__ == '__main__':
    main()
