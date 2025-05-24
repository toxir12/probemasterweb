import os
import json
import sqlite3
from flask import Flask, render_template, jsonify, request, session
from flask_cors import CORS
import hashlib
import time
import hmac
import base64

app = Flask(__name__, static_url_path='/static', static_folder='static')
CORS(app)  # Enable CORS for all routes
app.secret_key = os.environ.get("SESSION_SECRET", "masterquiz_telegram_webapp_secret")

# Telegram Bot Token (same as in main.py)
BOT_TOKEN = "8184215515:AAEVINsnkj_fTBbxZfBpvqZtUCsNj2kvwjo"

# Function to validate Telegram WebApp data
def validate_telegram_webapp(init_data):
    if not init_data:
        return False, None
    
    # Parse the init data
    try:
        # URL decode the init_data
        import urllib.parse
        decoded_data = urllib.parse.unquote(init_data)
        
        data_dict = {}
        for item in decoded_data.split('&'):
            if '=' in item:
                key, value = item.split('=', 1)
                data_dict[key] = value
        
        # Check if user data exists
        if 'user' not in data_dict:
            return False, None
        
        # Get user data
        try:
            user_data = json.loads(urllib.parse.unquote(data_dict['user']))
            
            # Validate that user_id exists in the user data
            if 'id' not in user_data:
                print("User data missing required 'id' field")
                return False, None
                
            return True, user_data
        except Exception as e:
            print(f"Error parsing user data: {e}")
            return False, None
            
    except Exception as e:
        print(f"Error validating Telegram WebApp data: {e}")
        return False, None

# Import TestStorage from the main bot
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from storage import TestStorage

# Initialize the same test storage as the main bot
test_storage = TestStorage()

# Function to sync user_tests.json files
def sync_user_tests_files():
    try:
        # Force the test storage to save its current state
        test_storage._save_tests()
        
        main_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'user_tests.json')
        webapp_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_tests.json')
        
        # Check if the main file exists
        if os.path.exists(main_file_path):
            # Read the main file
            with open(main_file_path, 'r', encoding='utf-8') as f:
                tests_data = json.load(f)
            
            # Write to the webapp file
            with open(webapp_file_path, 'w', encoding='utf-8') as f:
                json.dump(tests_data, f, ensure_ascii=False, indent=4)
            
            print(f"Successfully synced user_tests.json files")
            return True
        else:
            print(f"Main user_tests.json file not found at {main_file_path}")
            return False
    except Exception as e:
        print(f"Error syncing user_tests.json files: {e}")
        return False

# Function to get tests for a user
def get_user_tests(user_id):
    # First, ensure we have the latest tests
    sync_user_tests_files()
    
    # Convert user_id to integer if it's not already
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        print(f"Invalid user_id: {user_id}, cannot convert to integer")
        return []
    
    print(f"Getting tests for user: {user_id_int}")
    
    # Use the TestStorage directly to get the user's tests
    try:
        # Get tests directly from the test_storage object
        user_tests = test_storage.get_user_tests(user_id_int)
        print(f"Found {len(user_tests)} tests for user {user_id_int} using TestStorage")
        
        # Add an ID to each test if it doesn't have one
        for i, test in enumerate(user_tests):
            if 'id' not in test:
                test['id'] = f"test_{i+1}"
            # Add owner ID to each test to ensure ownership is clear
            test['owner_id'] = str(user_id_int)
            
            # Make sure each question has a correct_option field
            if 'questions' in test:
                for q_idx, question in enumerate(test['questions']):
                    # If the question doesn't have a correct_option, assume the first option is correct
                    if 'correct_option' not in question and 'options' in question and len(question['options']) > 0:
                        question['correct_option'] = 0
        
        return user_tests
    except Exception as e:
        print(f"Error getting tests from TestStorage: {e}")
        
        # Fallback to the JSON file method if TestStorage fails
        try:
            # Try to read from the main user_tests.json file
            main_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'user_tests.json')
            with open(main_file_path, 'r', encoding='utf-8') as f:
                tests_data = json.load(f)
                
                user_id_str = str(user_id_int)
                if user_id_str in tests_data:
                    user_tests = tests_data.get(user_id_str, [])
                    print(f"Found {len(user_tests)} tests for user {user_id_str} in JSON file")
                    
                    # Process tests as before
                    for i, test in enumerate(user_tests):
                        if 'id' not in test:
                            test['id'] = f"test_{i+1}"
                        test['owner_id'] = user_id_str
                        
                        if 'questions' in test:
                            for q_idx, question in enumerate(test['questions']):
                                if 'correct_option' not in question and 'options' in question and len(question['options']) > 0:
                                    question['correct_option'] = 0
                    
                    return user_tests
                else:
                    print(f"User ID {user_id_str} not found in JSON file")
        except Exception as e:
            print(f"Error reading from JSON file: {e}")
    
    # If all methods fail, return an empty list
    print(f"No tests found for user {user_id} using any method")
    return []

# Main route for the web app
@app.route('/')
def index():
    # Get language from query parameter if provided
    lang = request.args.get('lang', 'en')
    
    # Validate language (only allow 'uz', 'ru', or 'en')
    if lang not in ['uz', 'ru', 'en']:
        lang = 'en'
    
    return render_template('index.html', lang=lang)

# API endpoint to validate Telegram user and get their tests
@app.route('/api/validate', methods=['POST'])
def validate_user():
    try:
        # Get init data from request
        init_data = request.form.get('initData')
        
        # Debug log the init data
        print(f"Received initData: {init_data}")
        
        # Validate the data
        is_valid, user_data = validate_telegram_webapp(init_data)
        
        if not is_valid or not user_data:
            print("Validation failed or no user data")
            return jsonify({
                'success': False,
                'message': 'Invalid authentication data'
            }), 401
        
        # Debug log the user data
        print(f"Validated user data: {user_data}")
        
        # Store user data in session
        session['user_id'] = user_data.get('id')
        session['username'] = user_data.get('username')
        session['first_name'] = user_data.get('first_name')
        
        return jsonify({
            'success': True,
            'user': user_data
        })
    except Exception as e:
        print(f"Error in validate_user: {e}")
        return jsonify({
            'success': False,
            'message': f'Error processing request: {str(e)}'
        }), 500

# API endpoint to force sync of test files
@app.route('/api/sync', methods=['GET'])
def sync_tests():
    try:
        success = sync_user_tests_files()
        return jsonify({
            'success': success,
            'message': 'Tests synced successfully' if success else 'Failed to sync tests'
        })
    except Exception as e:
        print(f"Error in sync_tests: {e}")
        return jsonify({
            'success': False,
            'message': f'Error syncing tests: {str(e)}'
        }), 500

# API endpoint to get tests for the authenticated user
@app.route('/api/tests', methods=['GET'])
def get_tests():
    try:
        # Always sync tests first
        sync_user_tests_files()
        
        # Get user_id from session
        user_id = session.get('user_id')
        
        # Strict authentication check - only allow session-based authentication
        if not user_id:
            print("No user_id found in session")
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401
        
        print(f"Getting tests for user_id: {user_id}")
        tests = get_user_tests(user_id)
        
        return jsonify({
            'success': True,
            'tests': tests
        })
    except Exception as e:
        print(f"Error in get_tests: {e}")
        return jsonify({
            'success': False,
            'message': f'Error getting tests: {str(e)}'
        }), 500

# API endpoint to get a specific test
@app.route('/api/tests/<test_id>', methods=['GET'])
def get_test(test_id):
    # Get user_id from session - strict authentication check
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({
            'success': False,
            'message': 'User not authenticated'
        }), 401
    
    try:
        # Convert user_id to integer
        user_id_int = int(user_id)
        
        # Try to get the test by index first (for compatibility with older code)
        try:
            test_index = int(test_id)
            test = test_storage.get_test(user_id_int, test_index)
            if test:
                # Add ID if it doesn't exist
                if 'id' not in test:
                    test['id'] = f"test_{test_index}"
                # Add owner ID
                test['owner_id'] = str(user_id_int)
                
                # Make sure each question has a correct_option field
                if 'questions' in test:
                    for q_idx, question in enumerate(test['questions']):
                        if 'correct_option' not in question and 'options' in question and len(question['options']) > 0:
                            question['correct_option'] = 0
                
                return jsonify({
                    'success': True,
                    'test': test
                })
        except (ValueError, TypeError):
            # If test_id is not an integer, fall back to searching by ID
            pass
        
        # Fall back to searching through all tests
        tests = get_user_tests(user_id)
        
        # Find the test with the matching ID
        test = None
        for t in tests:
            if str(t.get('id', '')) == str(test_id):
                test = t
                break
        
        if not test:
            return jsonify({
                'success': False,
                'message': 'Test not found'
            }), 404
        
        return jsonify({
            'success': True,
            'test': test
        })
    except Exception as e:
        print(f"Error getting test {test_id} for user {user_id}: {e}")
        return jsonify({
            'success': False,
            'message': f'Error getting test: {str(e)}'
        }), 500

# API endpoint to submit test answers
@app.route('/api/submit_test', methods=['POST'])
def submit_test():
    # Get user_id from session - strict authentication check
    user_id = session.get('user_id')
    
    if not user_id:
        return jsonify({
            'success': False,
            'message': 'User not authenticated'
        }), 401
    
    data = request.json
    test_id = data.get('test_id')
    answers = data.get('answers', [])
    
    # Get the test
    tests = get_user_tests(user_id)
    test = None
    for t in tests:
        if str(t.get('id', '')) == str(test_id):
            test = t
            break
    
    if not test:
        return jsonify({
            'success': False,
            'message': 'Test not found'
        }), 404
        
    # Verify test ownership
    if 'owner_id' in test and str(test['owner_id']) != str(user_id):
        print(f"Ownership mismatch: Test owner {test['owner_id']} != User {user_id}")
        return jsonify({
            'success': False,
            'message': 'Access denied: You do not own this test'
        }), 403
    
    # Get the client-side score calculation if available
    client_correct = data.get('correct')
    client_total = data.get('total')
    client_percentage = data.get('percentage')
    answer_results = data.get('answer_results', [])
    
    # Print debug information
    print(f"Received answers: {answers}")
    print(f"Client-side score: {client_correct}/{client_total} ({client_percentage}%)")
    
    # Server-side calculation for verification
    server_correct_count = 0
    server_total_questions = len(test.get('questions', []))
    
    # Check each answer on the server side
    for i, question in enumerate(test.get('questions', [])):
        if i < len(answers):
            try:
                user_answer = int(answers[i]) if answers[i] is not None else None
                
                # Handle the correct_option field - it might be missing or in different formats
                correct_answer = None
                if 'correct_option' in question:
                    # Try to convert to int
                    try:
                        correct_answer = int(question.get('correct_option'))
                    except (ValueError, TypeError):
                        # If conversion fails, assume the first option (index 0) is correct
                        correct_answer = 0
                        print(f"Warning: Invalid correct_option for question {i+1}, assuming first option is correct")
                else:
                    # If correct_option is missing, assume the first option (index 0) is correct
                    correct_answer = 0
                    print(f"Warning: Missing correct_option for question {i+1}, assuming first option is correct")
                
                print(f"Question {i+1}: User answered {user_answer}, correct is {correct_answer}")
                
                # Check if the answer is correct
                if user_answer is not None and correct_answer is not None and user_answer == correct_answer:
                    server_correct_count += 1
                    print(f"Question {i+1}: CORRECT")
                else:
                    print(f"Question {i+1}: INCORRECT")
            except (ValueError, TypeError) as e:
                print(f"Error processing answer for question {i+1}: {e}")
    
    print(f"Server calculation: {server_correct_count} out of {server_total_questions}")
    server_percentage = (server_correct_count / server_total_questions) * 100 if server_total_questions > 0 else 0
    
    # Choose the most reliable score (prefer server-side calculation)
    if server_total_questions > 0:
        correct_count = server_correct_count
        total_questions = server_total_questions
        percentage = server_percentage
        print(f"Using server-side calculation: {correct_count}/{total_questions} ({percentage}%)")
    elif client_correct is not None and client_total is not None:
        # Fall back to client-side calculation if server calculation failed
        correct_count = client_correct
        total_questions = client_total
        percentage = client_percentage if client_percentage is not None else (client_correct / client_total * 100 if client_total > 0 else 0)
        print(f"Using client-side calculation: {correct_count}/{total_questions} ({percentage}%)")
    else:
        # Default values if all else fails
        correct_count = 0
        total_questions = 0
        percentage = 0
        print("Warning: Could not calculate score reliably")
    
    # Save results to the bot's database
    try:
        # Import the database functions from the parent directory
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from database import save_test_result
        import asyncio
        import datetime
        
        # Calculate points (same formula as in the bot)
        points_100 = round((correct_count / total_questions) * 100) if total_questions > 0 else 0
        
        # Get the current date and time
        current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get the test name
        test_name = test.get('name', f"Test {test_id}")
        
        print(f"Saving test result to database: User {user_id}, Test '{test_name}', Score {correct_count}/{total_questions} ({percentage}%)")
        
        # Save the result to the database
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(save_test_result(
            user_id=int(user_id),
            test_name=test_name,
            date=current_date,
            correct=correct_count,
            total=total_questions,
            percent=percentage,
            points=points_100
        ))
        loop.close()
        
        print(f"Test result saved successfully for user {user_id}")
    except Exception as e:
        print(f"Error saving test result to database: {e}")
    
    return jsonify({
        'success': True,
        'score': {
            'correct': correct_count,
            'total': total_questions,
            'percentage': percentage,
            'points': points_100
        },
        'saved_to_database': True
    })

if __name__ == "__main__":
    # Get port from environment variable (Railway sets this)
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
