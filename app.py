from flask import Flask, render_template, request, redirect, url_for, flash,jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_jwt_extended import JWTManager, create_access_token
from werkzeug.security import generate_password_hash, check_password_hash
import numpy as np
import random 
import re
import json
import os
from scraper import get_gameweek_teams, get_results
from datetime import datetime,timedelta

app = Flask(__name__)
app.config.from_object('config.Config')
jwt = JWTManager(app)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class League(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)
    user_ids = db.Column(db.Text,default='[]')
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def add_user_id(self, user_id):
        if self.user_ids:
            user_ids = json.loads(self.user_ids)
        else:
            user_ids = []

        user_ids += [user_id]
        user_ids = list(set(user_ids))
        self.user_ids = json.dumps(user_ids)
        db.session.commit()

# Initial empty dictionary for game week teams (to be stored in DB)
class GameWeekTeams(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Text, nullable=False)
    start_time = db.Column(db.TIMESTAMP)

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)
    score = db.Column(db.Float, default=0.0)
    gold = db.Column(db.Integer, default=380)
    team_choice = db.Column(db.String(50))  # Nullable by default, starts as None
    locked_team_choice = db.Column(db.String(50))
    previous_results = db.Column(db.Text)  # JSON string to store previous results
    delayed_matches = db.Column(db.Text) # JSON string for cancelled matches
    league_ids = db.Column(db.Text, default='[]')
    doubleup = db.Column(db.Boolean, default=False)
    doubleupsleft = db.Column(db.Integer, default = 2)


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def add_previous_result(self, team, score):
        if self.previous_results:
            previous_results_dict = json.loads(self.previous_results)
        else:
            previous_results_dict = {}

        # Add new result
        round_number = len(previous_results_dict) + 1
        previous_results_dict[round_number] = {'team': team, 'score': score}

        # Update and save to database
        self.previous_results = json.dumps(previous_results_dict)
        db.session.commit()

    def add_delayed_matches(self, team):
        if self.delayed_matches:
            delayed_matches_list = json.loads(self.delayed_matches)
        else:
            delayed_matches_list = []

        # Add new result
        delayed_matches_list+=[team]

        # Update and save to database
        self.delayed_matches = json.dumps(delayed_matches_list)
        db.session.commit()

    def remove_delayed_matches(self, team):
        if self.delayed_matches:
            delayed_matches_list = json.loads(self.delayed_matches)
        else:
            delayed_matches_list = []

        # Add new result
        if team in delayed_matches_list:
            delayed_matches_list = delayed_matches_list.remove(team)

        # Update and save to database
        self.delayed_matches= json.dumps(delayed_matches_list)
        db.session.commit()

    def add_league_id(self, league_id):
        if self.league_ids:
            league_ids = json.loads(self.league_ids)
        else:
            league_ids = []

        league_ids += [league_id]
        league_ids = list(set(league_ids))
        self.league_ids = json.dumps(league_ids)
        db.session.commit()


# Admin model
class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Create all database tables
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    # Check if user is an Admin
    user = User.query.get(int(user_id))
    if user:
        return user
    else:
        return Admin.query.get(int(user_id))

# Function to update game week teams in DB
def update_gameweek_teams(data, start_gameweek):
    gameweek_teams = GameWeekTeams.query.first()
    if gameweek_teams:
        gameweek_teams.data = json.dumps(data)
        gameweek_teams.start_time = start_gameweek
    else:
        new_gameweek_teams = GameWeekTeams(data=json.dumps(data),start_time = start_gameweek)
        db.session.add(new_gameweek_teams)
    db.session.commit()

# Function to read current game week teams from DB
def read_current_gameweek_teams():
    gameweek_teams = GameWeekTeams.query.first()
    if gameweek_teams:
        if gameweek_teams.data is None:
            return {}
        else:
            return json.loads(gameweek_teams.data)
    else:
        return {}

def give_gold(amount):
    users = User.query.all()
    for user in users:
        user.gold += amount

def lock_team_choices():
    users = User.query.all()
    teams = read_current_gameweek_teams()
    for user in users:
        if user.team_choice is not None:
            for key, value in teams.items():
                if key == user.team_choice:
                    user.gold -= value
                    user.locked_team_choice = key
                    if user.doubleup:
                        if user.gold >= value:
                            user.gold -= value
                        else:
                            user.doubleup = False
                    break
        else:
            random_value = np.random.randint(1,9)
            for key, value in teams.items():
                if value == random_value:
                    user.gold -= 10
                    user.locked_team_choice = key
                    break
        ## Option to add strategies
        user.team_choice = None
    
    # Calculate the new time
    new_time = datetime.now() + timedelta(days=100)
    
    # Update the record's start_time
    

    teams = {}
    update_gameweek_teams(teams, new_time)

# Function to update scores and reset team choices
def update_scores():
    winner_scores = get_results()
    users = User.query.all()
    for user in users:
        ###ADD Previous delayed_matches
        if user.delayed_matches is not None:
            for match in user.delayed_matches:
                score_for_round = None 

                if match in winner_scores:
                    score_for_round = winner_scores[user.locked_team_choice]
                if match[0:3] == 'Lei':  
                    score_for_round += 0.1 
                if score_for_round is not None:
                    user.score += score_for_round
                    user.score = format(user.score, '.1f')
                    user.add_previous_result(match, score_for_round)
                    user.remove_delayed_matches(match)

        ###Add current round
        score_for_round = None 
        if user.locked_team_choice in winner_scores:
            score_for_round = winner_scores[user.locked_team_choice]
            if user.doubleup and user.doubleupsleft > 0.5:
                score_for_round += winner_scores[user.locked_team_choice]
                user.doubleupsleft -= 1          
                user.doubleup = False  
        if user.locked_team_choice is not None:
            if user.locked_team_choice[0:3] == 'Lei':
                score_for_round += 0.1
        if score_for_round is not None:
            user.score += score_for_round
            user.add_previous_result(user.locked_team_choice, score_for_round)
        else:
            user.add_delayed_matches(user.locked_team_choice)
        user.team_choice = None
        user.locked_team_choice = None
        db.session.commit()

# Routes
@app.route('/')
@login_required
def index():
    if current_user.username == 'admin':
        return redirect(url_for('admin'))
    else:
        return redirect(url_for('home', username=current_user.username))

@app.route('/home/<username>')
@login_required
def home(username):
    user = User.query.filter_by(username=username).first()
    admin = User.query.filter_by(username=username).first()
    if admin.previous_results is None:
        round = 1
    else:
        if user.delayed_matches is not None:
            round = len(json.loads(admin.previous_results)) +len(json.loads(admin.delayed_matches)) +1
        else:
            round = len(json.loads(admin.previous_results)) +1 

    teams = read_current_gameweek_teams()
    teams_new_string = {}
    for key,value in teams.items():
        teams_new_string[transform_match_string(key)] = value
    if teams is None:
        teams = {}
    return render_template('home.html', username=username, score=user.score, gold=user.gold, team_choice=transform_match_string(user.team_choice),locked_team_choice= transform_match_string(user.locked_team_choice), teams=teams_new_string, round = round, doubleup = user.doubleup, doubleupsleft = user.doubleupsleft)

@app.route('/choose_team', methods=['POST'])
@login_required
def choose_team():
    transformed_team_name = request.form.get('team')
    team_name = inverse_transform_match_string(transformed_team_name)
    if team_name:
        user = current_user

        # Get game week teams
        teams = read_current_gameweek_teams()

        # Check if selected team exists and user has enough gold
        if team_name in teams and user.gold >= teams[team_name]:
            # Return gold from previous pick if changing team choice

            # Update user's team choice and deduct gold for new choice
            user.team_choice = team_name
            db.session.commit()
            flash(f'Team {team_name} chosen successfully. Gold deducted: {teams[team_name]}', 'success')
        else:
            flash('Invalid team selection or not enough gold.', 'error')

    return redirect(url_for('home', username=current_user.username))

@app.route('/update_doubleup', methods=['POST'])
def update_doubleup():
    # Retrieve data from the request
    doubleup_state = request.json.get('doubleup')
    
    # Assuming current_user is logged in
    current_user.doubleup = doubleup_state
    
    # Save to the database
    db.session.commit()
    return jsonify({"success": True, "doubleup": current_user.doubleup})

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if User.query.filter_by(username=username).first() or Admin.query.filter_by(username=username).first():
            flash('Username already exists. Please choose a different one.', 'error')
            return redirect(url_for('signup'))

        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/keep-alive')
def keep_alive():
    gameweek_teams = GameWeekTeams.query.first()  # Retrieve the first record
    if not gameweek_teams:
        return "I'm alive!", 200

    start_time = gameweek_teams.start_time
    now = datetime.now()

    if now > start_time:
        lock_team_choices()  # Call the lock function if the condition is met
        


    return "I'm alive!", 200


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))



@app.route('/admin')
@login_required
def admin():
    if current_user.username == 'admin':
        return render_template('admin.html')
    else:
        flash('Unauthorized access.', 'error')
        return redirect(url_for('index'))




@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        admin = Admin.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully.', 'success')
            if username == 'admin':
                return redirect(url_for('admin'))
            else:
                return redirect(url_for('home', username=username))  # Redirect to home page with username
        elif admin and admin.check_password(password):
            login_user(admin)
            flash('Logged in as admin.', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Incorrect username or password.', 'error')

    return render_template('login.html')




@app.route('/previous_results/<username>')
@login_required
def previous_results(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('home', username=current_user.username))

    previous_results_dict = json.loads(user.previous_results or '{}')

    return render_template('previous_results.html', username=username, previous_results=previous_results_dict)

@app.route('/join_league', methods=['POST'])
@login_required
def join_league():
    league_name = request.form['league_name']
    password = request.form['league_password']
    
    league = League.query.filter_by(name=league_name).first()
    
    if league and league.check_password(password):
        user_ids = json.loads(league.user_ids)
        if current_user.id not in user_ids:
            current_user.add_league_id(league.id)
            league.add_user_id(current_user.id)
            db.session.commit()
            flash('Successfully joined the league!', 'success')
        else:
            flash('You are already a member of this league.', 'info')
    else:
        flash('Invalid league name or password.', 'error')
    
    return redirect(url_for('home', username=current_user.username))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check if the username already exists
        if User.query.filter_by(username=username).first() or Admin.query.filter_by(username=username).first():
            flash('Username already exists. Please choose a different one.', 'error')
            return redirect(url_for('login'))

        # Create a new user
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()

            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

    
@app.route('/generate_teams', methods=['POST'])
@login_required
def generate_teams():
    if current_user.username == 'admin':
        if current_user.previous_results is None:
            round = None
        else:
            round = len(json.loads(current_user.previous_results)) +len(json.loads(current_user.delayed_matches)) +1

        print (round)
        # Example function call to generate new game week teams
        new_teams, start_gameweek = get_gameweek_teams(round)
        update_gameweek_teams(new_teams, start_gameweek)
        # Update all users with new teams (example logic)
        users = User.query.all()
        for user in users:
            user.team_choice = None  # Reset team choice
            #user.gold = 100  # Reset gold (example logic)
            db.session.commit()

        flash('New teams generated successfully.', 'success')
    else:
        flash('Unauthorized access.', 'error')

    return redirect(url_for('admin'))

@app.route('/update_scores', methods=['POST'])
@login_required
def update_scores_route():
    if current_user.username == 'admin':
        update_scores()
        flash('Scores updated successfully.', 'success')
    else:
        flash('Unauthorized access.', 'error')

    return redirect(url_for('admin'))

@app.route('/lock_team_choices', methods=['POST'])
@login_required
def lock_team_choices_route():
    if current_user.username == 'admin':
        lock_team_choices()
        flash('Team choices locked successfully.', 'success')
    else:
        flash('Unauthorized access.', 'error')

    return redirect(url_for('admin'))

@app.route('/show_league_scores/<league_id>')
@login_required
def show_league_scores(league_id):
    league = League.query.filter_by(id = league_id).first()
    user_ids = json.loads(league.user_ids)
    print (user_ids, type(user_ids))
    users = [User.query.get(user_id) for user_id in user_ids]
    print (users)
    return render_template('scores.html', users=users)



@app.route('/show_scores')
@login_required
def show_scores():
    users = User.query.all()  # Fetch all users
    print (type(users[0]))
    return render_template('scores.html', users=users)

@app.route('/show_leagues/<username>')
@login_required
def show_leagues(username):

    user = User.query.filter_by(username=username).first()
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('home', username=current_user.username))

    leagues = json.loads(user.league_ids)
    return render_template('user_leagues.html',username=username,league_ids = leagues)

@app.route('/create_league', methods=['POST'])
@login_required
def create_league():
    if current_user.username != 'admin':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('index'))

    league_name = request.form.get('league_name')
    league_password = request.form.get('league_password')

    if League.query.filter_by(name=league_name).first():
        flash('League name already exists. Please choose a different name.', 'error')
        return redirect(url_for('admin'))

    new_league = League(name=league_name)
    new_league.set_password(league_password)
    db.session.add(new_league)
    db.session.commit()

    flash('League created successfully!', 'success')
    return redirect(url_for('admin'))



@app.route('/loginIOS', methods=['POST'])
def loginIOS():

    data = request.json
    username = data.get('username')
    password = data.get('password')
    user = User.query.filter_by(username=username).first()
    admin = User.query.filter_by(username="admin").first()
    teams = read_current_gameweek_teams()
    teams_new_string = {}
    for key,value in teams.items():
        teams_new_string[transform_match_string(key)] = value
    if admin.previous_results is None:
        round = 1
    else:
        if user.delayed_matches is not None:
            round = len(json.loads(admin.previous_results)) +len(json.loads(admin.delayed_matches)) +1
        else:
            round = len(json.loads(admin.previous_results)) +1 


            
    if user and user.check_password(password):
        token = create_access_token(identity=username)
        if user.team_choice is None:
            team_choice = ""
        else:
            team_choice = transform_match_string(user.team_choice)
        if user.locked_team_choice is None:
            locked_team_choice = ""
        else:
            locked_team_choice = transform_match_string(user.locked_team_choice)
        return jsonify({
            'access_token': token,
            'username': user.username,
            'score': user.score,
            'gold': user.gold,
            'team_choice': team_choice,
            'locked_team_choice': locked_team_choice,
            'round': round,
            'teams': teams_new_string 
        }), 200
    return jsonify({"msg": "Invalid username or password"}), 401




@app.route('/choose_teamIOS', methods=['POST'])
def choose_teamIOS():
    data = request.json
    transformed_team_name = data.get('team_name')
    username = data.get('username')
    admin = User.query.filter_by(username="admin").first()

    if transformed_team_name == None or transformed_team_name == '':
        return jsonify({"msg": "team not selected"}), 401

    team_name = inverse_transform_match_string(transformed_team_name)
    user = User.query.filter_by(username=username).first()


        # Get game week teams
    teams = read_current_gameweek_teams()

        # Check if selected team exists and user has enough gold
    if team_name in teams and user.gold >= teams[team_name]:
        # Return gold from previous pick if changing team choice

        # Update user's team choice and deduct gold for new choice
        user.team_choice = team_name
        db.session.commit()
    else:
        return jsonify({"msg": "Not enough gold"}), 401



    teams_new_string = {}
    for key,value in teams.items():
        teams_new_string[transform_match_string(key)] = value
    if admin.previous_results is None:
        round = 1
    else:
        if user.delayed_matches is not None:
            round = len(json.loads(admin.previous_results)) +len(json.loads(admin.delayed_matches)) +1
        else:
            round = len(json.loads(admin.previous_results)) +1 
    
    if user.team_choice is None:
        team_choice = ""
    else:
        team_choice = transform_match_string(user.team_choice)
    if user.locked_team_choice is None:
        locked_team_choice = ""
    else:
        locked_team_choice = transform_match_string(user.locked_team_choice)
    return jsonify({
        'access_token': "",
        'username': user.username,
        'score': user.score,
        'gold': user.gold,
        'team_choice': team_choice,
        'locked_team_choice': locked_team_choice,
        'round': round,
        'teams': teams_new_string 
    }), 200



@app.route('/getLeaguesIOS', methods=['POST'])
def get_leaguesIOS():
    try:
        # Parse input JSON
        data = request.get_json()
        username = data.get("username")

        # Validate input
        if not username:
            return jsonify({"error": "Username is required"}), 400

        # Retrieve leagues for the user (mock data for demonstration)
        user = User.query.filter_by(username=username).first()

        user_leagues = json.loads(user.league_ids)

        # Add the global "Worldwide" league
        all_leagues = ["Worldwide"] + ['ABC'] + user_leagues

        # Return the list of leagues
        return jsonify({"leagues": all_leagues}), 200

    except Exception as e:
        # Handle unexpected errors
        return jsonify({"error": str(e)}), 500

def transform_match_string(input_string):
    if input_string is None:
        return None
    # Step 1: Replace the first underscore with " Vs "
    transformed_string = input_string.replace('_', ' vs ', 1)
    # Step 3: Replace _H with home emoji and _A with away emoji
    transformed_string = transformed_string.replace('_H', ' 🏠')  # Home emoji
    transformed_string = transformed_string.replace('_A', ' 🌍')  # Away emoji (Globe + Airplane)


    return transformed_string


def inverse_transform_match_string(transformed_string):
    if transformed_string is None:
        return None
    # Step 1: Replace " Vs " with the first underscore
    inverse_string = transformed_string.replace(' vs ', '_', 1)
    
    
    # Step 3: Replace home and away emojis with _H and _A respectively
    inverse_string = inverse_string.replace(' 🏠', '_H')  # Home emoji back to _H
    inverse_string = inverse_string.replace(' 🌍', '_A')  # Away emoji back to _A

    return inverse_string



if __name__ == '__main__':
    #create_database()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

