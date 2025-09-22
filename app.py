from flask import Flask, render_template, request, redirect, url_for, flash,jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_jwt_extended import JWTManager, create_access_token
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import numpy as np
import dateparser
import math
import re
import json
import os
from scraper import get_gameweek_teams, get_results, get_round_scores, get_next_start_time
from datetime import datetime,timedelta
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itsdangerous import URLSafeTimedSerializer
import smtplib
import pandas as pd

TEAM_MAPS = {"Burnley":"BUR","Sunderland":"SUN","Leeds": "LEE","Leicester": "LEI", "ManchesterCity":"MCI","Liverpool":"LIV","WestHam":"WHU","Chelsea":"CHE","Ipswich":"IPS","Arsenal":"ARS","Brentford":"BRE","CrystalPalace":"CRY","Southampton":"SOU","Tottenham":"TOT","Wolves":"Wol","AstonVilla":"AVL","Brighton":"BHA","Fulham":"FUL","Bournemouth":"BOU","Newcastle":"NEW","ManchesterUtd":"MUN","Everton":"EVE","Nottingham":"NFO"}
REVERSE_TEAM_MAPS = {value:key for key,value in TEAM_MAPS.items()}

app = Flask(__name__)
app.config.from_object('config.Config')
CORS(app, resources={r"/*": {"origins": "*"}})

jwt = JWTManager(app)
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@app.route('/live-fixtures', methods=['GET'])
def live_fixtures():
    gameweek_teams = GameWeekTeams.query.first()
    results = json.loads(gameweek_teams.round_results)
    return jsonify({"fixtures": results})

class GameweekStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    gameweek = db.Column(db.Integer, nullable=False)
    gold = db.Column(db.Text, nullable=False)      # Store as JSON string
    points = db.Column(db.Text, nullable=False)    # Store as JSON string
    ex_points = db.Column(db.Text, nullable=False)    # Store as JSON string
    goal_difference = db.Column(db.Text, nullable=False)    # Store as JSON string



    def set_gold(self, gold_dict):
        self.gold = json.dumps(gold_dict)

    def get_gold(self):
        return json.loads(self.gold)

    def set_points(self, points_dict):
        self.points = json.dumps(points_dict)

    def get_points(self):
        return json.loads(self.points)
    
    def set_ex_points(self, ex_points_dict):
        self.ex_points = json.dumps(ex_points_dict)

    def get_ex_points(self):
        return json.loads(self.ex_points)
    
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
    end_time = db.Column(db.TIMESTAMP)
    round_results = db.Column(db.Text)
    next_start_time = db.Column(db.TIMESTAMP)


# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True)
    password_hash = db.Column(db.String(150), nullable=False)
    score = db.Column(db.Float, default=0.0)
    gold = db.Column(db.Integer, default=400)
    team_choice = db.Column(db.String(50))  # Nullable by default, starts as None
    locked_team_choice = db.Column(db.String(50))
    previous_results = db.Column(db.Text)  # JSON string to store previous results
    delayed_matches = db.Column(db.Text) # JSON string for cancelled matches
    league_ids = db.Column(db.Text, default='[]')
    doubleup = db.Column(db.Boolean, default=False)
    doubleupsleft = db.Column(db.Integer, default = 2)
    rank = db.Column(db.Integer, default = 1)
    GD_bonus = db.Column(db.Boolean, default=False)
    GD_bonus_left = db.Column(db.Integer, default = 1)
    gd = db.Column(db.Integer,default = 0)
    handicap_bonus = db.Column(db.Boolean, default=False)
    handicap_bonus_left = db.Column(db.Integer, default = 1)

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

    def add_delayed_matches(self, team, double_jeopardy, gd_bonus, handicap_bonus):
        if self.delayed_matches:
            delayed_matches_list = json.loads(self.delayed_matches)
        else:
            delayed_matches_list = []

        # Add new result
        output = {"team":team,"DJ":double_jeopardy,"GD":gd_bonus, "HB":handicap_bonus}
        if delayed_matches_list is None:
            delayed_matches_list = [output]
        else:
            delayed_matches_list+=[output]

        # Update and save to database
        self.delayed_matches = json.dumps(delayed_matches_list)
        db.session.commit()

    def remove_delayed_matches(self, team):
        a=1
        if self.delayed_matches:
            delayed_matches_list = json.loads(self.delayed_matches)
        else:
            delayed_matches_list = []


        # Add new result
        for team_dict in delayed_matches_list:
            if team == team_dict['team']:
                delayed_matches_list = delayed_matches_list.remove(team_dict)

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


def add_results_to_gameweek(results):
    gameweek_teams = GameWeekTeams.query.first()

    if gameweek_teams:
        # Assuming there's a column named `results_json` to store JSON data
        gameweek_teams.round_results = json.dumps(results)  # Convert Python dict to JSON string
        db.session.commit()  # Save changes to the database
    else:
        print("No GameWeekTeams entry found.")


# Function to update game week teams in DB
def update_gameweek_teams(data, start_gameweek, end_gameweek, next_start_gameweek):
    gameweek_teams = GameWeekTeams.query.first()
    if gameweek_teams:
        gameweek_teams.data = json.dumps(data)
        gameweek_teams.start_time = start_gameweek
        if end_gameweek is not None:
            gameweek_teams.end_time = end_gameweek
    else:
        if end_gameweek is not None:
            new_gameweek_teams = GameWeekTeams(data=json.dumps(data),start_time = start_gameweek, end_time = end_gameweek, next_start_time = next_start_gameweek)
        else:
            new_gameweek_teams = GameWeekTeams(data=json.dumps(data),start_time = start_gameweek, end_time = end_gameweek, next_start_time = next_start_gameweek)
        db.session.add(new_gameweek_teams)
    db.session.commit()

# Function to read current game week teams from D
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
                    if user.gold >= value:
                        user.gold -= value
                        user.locked_team_choice = key
                        if user.doubleup:
                            if user.gold >= value:
                                user.gold -= value
                            else:
                                user.doubleup = False


                    else:
                        user.locked_team_choice = None
                    break
        else:
            user.locked_team_choice = ''
            user.gold -= 1
            #random_value = np.random.randint(1,5)
            #for key, value in teams.items():
            #    if value == random_value:
            #        user.gold -= 10
            #        user.locked_team_choice = key
            #        break
        ## Option to add strategies
        user.team_choice = None
    
    # Calculate the new time
    new_time = datetime.now() + timedelta(days=100)
    
    # Update the record's start_time
    

    teams = {}
    update_gameweek_teams(teams, new_time,None, None)

def points_from_GD(GD):
    if GD>0:
        score_for_round = 3
    elif GD<0:
        score_for_round = 0
    else:
        score_for_round = 1
    return score_for_round

# Function to update scores and reset team choices
def update_scores():
    gameweek_teams =read_current_gameweek_teams()

    winner_scores = get_results()
    # Get first row
    #if len(gameweek_teams) < 5:
    #    raise ValueError('Gameweek Teams Failiure')
    fixtures = [str(key) for key in gameweek_teams.keys()]
    #if len(fixtures) < 5:
    #    raise ValueError('Fixtures Teams Failiure')
    print (fixtures,11111111111)
    winner_scores_round = {key:val for key, val in winner_scores.items() if str(key) in fixtures}
    #if len(winner_scores_round) < 5:
    #    raise ValueError('Winner Scores Teams Failiure')
    scores_for_db = {key.split('_')[0]:points_from_GD(value) for key,value in winner_scores_round.items()}
    #if len(scores_for_db) < 5:
    #    raise ValueError('SCORES_FOR_DB Teams Failiure')
    gd_for_db = {key.split('_')[0]:value for key,value in winner_scores_round.items()}
    # Find the most recent GameweekStats row with empty points
    row = GameweekStats.query.filter_by(points='{}').order_by(GameweekStats.id.desc()).first()
    if row:
        row.points = json.dumps(scores_for_db)
        row.goal_difference = json.dumps(gd_for_db)

        db.session.commit()
    else:
        print("No row found with empty points.")

    users = User.query.all()
    for user in users:
        print (user,11111111)
        ###ADD Previous delayed_matches
        if user.delayed_matches is not None:
            a = json.loads(user.delayed_matches)
            if a is not None:
                for match_dict in json.loads(user.delayed_matches):
                    if match_dict is not None:
                        match = match_dict['team']
                        double_jepordy = match_dict['DJ']
                        gd_bonus = match_dict['GD']
                        handicap_bonus = match_dict['HB']
                        score_for_round = None 

                        if match in winner_scores:
                            GD = winner_scores[match]
                            if handicap_bonus:
                                score_for_round = points_from_GD(GD+2)
                            else:
                                score_for_round = points_from_GD(GD)
                            if double_jepordy:
                                score_for_round +=points_from_GD(GD)
                            if gd_bonus:
                                score_for_round += GD
                            if match[0:3] == 'Lei':  
                                score_for_round += 0.1 
                        if score_for_round is not None:
                            user.score += score_for_round
                            user.score = format(user.score, '.1f')
                            user.add_previous_result(match, score_for_round)
                            user.remove_delayed_matches(match)
                            user.gd += GD

        ###Add current round
        score_for_round = None 
        if user.locked_team_choice in winner_scores:
            GD = winner_scores[user.locked_team_choice]
            if user.handicap_bonus and user.handicap_bonus_left > 0.5:
                score_for_round = points_from_GD(GD + 2)
                user.handicap_bonus_left -=1
                user.handicap_bonus = False
            else:
                score_for_round = points_from_GD(GD)
            if user.doubleup and user.doubleupsleft > 0.5:
                score_for_round +=points_from_GD(GD)
                user.doubleupsleft -= 1          
                user.doubleup = False  
            if user.GD_bonus and user.GD_bonus_left > 0.5:
                score_for_round += GD
                user.GD_bonus_left -= 1
                user.GD_bonus = False
            if user.locked_team_choice[0:3] == 'Lei':
                score_for_round += 0.1
        elif user.locked_team_choice is '':
            score_for_round = 0

            GD = 0
        else:
            score_for_round = None
        if score_for_round is not None:
            user.score += score_for_round
            user.gd += GD
            user.score = format(user.score, '.1f')
            user.add_previous_result(user.locked_team_choice, score_for_round)
        elif user.locked_team_choice is not None:
            if user.doubleup:
                user.doubleupsleft -= 1
            if user.GD_bonus:
                user.GD_bonus_left -= 1
            if user.handicap_bonus:
                user.handicap_bonus_left -= 1
            user.add_delayed_matches(user.locked_team_choice, user.doubleup,user.GD_bonus, user.handicap_bonus)
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
    admin = User.query.filter_by(username='admin').first()
    if admin.previous_results is None:
        round = 1
    else:
        if admin.delayed_matches is not None:
            round = len(json.loads(admin.previous_results)) +len(json.loads(admin.delayed_matches)) 
        else:
            round = len(json.loads(admin.previous_results)) +1 

    teams = read_current_gameweek_teams()
    teams_new_string = {}
    for key,value in teams.items():
        teams_new_string[transform_match_string(key)] = value
    if teams is None:
        teams = {}
    return render_template('home.html', username=username, score=user.score, gold=user.gold, team_choice=transform_match_string(user.team_choice),locked_team_choice= transform_match_string(user.locked_team_choice), teams=teams_new_string, round = round, doubleup = user.doubleup, doubleupsleft = user.doubleupsleft, gdbonus = user.GD_bonus, gdbonusleft = user.GD_bonus_left)

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
    if current_user.doubleupsleft >0:
        current_user.doubleup = doubleup_state
    
    # Save to the database
    db.session.commit()
    return jsonify({"success": True, "doubleup": current_user.doubleup})

@app.route('/update_gdbonus', methods=['POST'])
def update_gdbonus():
    # Retrieve data from the request
    gdbonus_state = request.json.get('gdbonus')
    
    # Assuming current_user is logged in
    if current_user.GD_bonus_left > 0:
        current_user.GD_bonus = gdbonus_state
    
    # Save to the database
    db.session.commit()
    return jsonify({"success": True, "gdbonus": current_user.GD_bonus})

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
    end_time = gameweek_teams.end_time
    email_time = start_time - pd.Timedelta(minutes=60*23)
    now = datetime.now()

    if now > end_time:
        try:
    
            row = GameWeekTeams.query.get(1)        
            gameweek_teams = get_gameweek_teams()      # fetch the first row (id=1)
            if not row:
                raise RuntimeError("Row id=1 not found")

            row.end_time = datetime.now() + timedelta(days=100)
            db.session.commit()
            update_scores()
            generate_teams_auto()
            return "updated scores",200
        except AttributeError: 
            return "failed updating scores", 200

    if now > start_time - pd.Timedelta(minutes=30):
        lock_team_choices()  # Call the lock function if the condition is met
        return "team choices locked", 200
        
    if 0 < (email_time - now).total_seconds() < 305:
        count = sent_reminder_email()
        return f"{count} Emails sent!", 200

    admin = User.query.filter_by(username='admin').first()
    if admin.previous_results is None:
        round = 1
    else:
        if admin.delayed_matches is not None:
            round = len(json.loads(admin.previous_results)) +len(json.loads(admin.delayed_matches)) 
        else:
            round = len(json.loads(admin.previous_results)) +1 
    try:
        results = get_round_scores(round)
        add_results_to_gameweek(results)
    except AttributeError:
        pass

    return "I'm alive!", 200

def sent_reminder_email():
    count = 0
    users = User.query.all()
    for user in users:
        print (user.username)
        if user.email is not None:
            if user.team_choice is None:
                body = f"""Hello {user.username}, 
                Reminder that teams will be locked in approximately 23 hours, please choose your team, 
                https://premier-league-predictions-2.onrender.com/
                Not sure who to pick? Have a look at our experts Golden Three picks https://goldenpicksdotblog.wordpress.com/
                Best regards
                The Golden Picks team."""
                send_email('goldenpicks2025@gmail.com', "hihy jobv qtmr zvxl", user.email, "Golden Picks Reminder", body)
                count += 1
            else:
                continue
        else:
            continue
    return count
        




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
        email = request.form['email']

        # Check if the username already exists
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash('Username already exists. Please choose a different one.', 'error')
            return redirect(url_for('login'))

        # Create a new user
        else:
            new_user = User(username=username, email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()

            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

def generate_teams_auto():
    current_user = User.query.filter_by(username='admin').first()
    if current_user.previous_results is None:
        round = 1
    elif current_user.delayed_matches is None:
        round = len(json.loads(current_user.previous_results)) + 1
    else:
        round = len(json.loads(current_user.previous_results)) +len(json.loads(current_user.delayed_matches)) 

    # Example function call to generate new game week teams
    new_teams,exp_points, start_gameweek, end_gameweek = get_gameweek_teams(round)
    teams_for_db = {key.split('_')[0]:value for key,value in new_teams.items()}
    ex_points_for_db = {key.split('_')[0]:value for key,value in exp_points.items()}

    next_start_gameweek = get_next_start_time(round + 1)
    update_gameweek_teams(new_teams, start_gameweek, end_gameweek, next_start_gameweek)
    # Update all users with new teams (example logic)
    gameweek_entry = GameweekStats(
        gameweek=round,
        gold=json.dumps(teams_for_db),
        points=json.dumps({}),
        ex_points = json.dumps(ex_points_for_db),
        goal_difference = json.dumps({}),
    )
    db.session.add(gameweek_entry)
    db.session.commit()
    users = User.query.all()
    for user in users:
        user.team_choice = None  # Reset team choice
    db.session.commit()
    
@app.route('/generate_teams', methods=['POST'])
@login_required
def generate_teams():
    if current_user.username == 'admin':
        if current_user.previous_results is None:
            round = 1
        elif current_user.delayed_matches is None:
            round = len(json.loads(current_user.previous_results)) + 1
        else:
            round = len(json.loads(current_user.previous_results)) +len(json.loads(current_user.delayed_matches)) 

        print (round)
        # Example function call to generate new game week teams
        new_teams,exp_points, start_gameweek, end_gameweek = get_gameweek_teams(round)
        update_gameweek_teams(new_teams, start_gameweek, end_gameweek, None)
        teams_for_db = {key.split('_')[0]:value for key,value in new_teams.items()}
        ex_points_for_db = {key.split('_')[0]:value for key,value in exp_points.items()}

        gameweek_entry = GameweekStats(
            gameweek=round,
            gold=json.dumps(teams_for_db),
            points=json.dumps({}),
            ex_points = json.dumps(ex_points_for_db),
            goal_difference= json.dumps({}),

        )
        db.session.add(gameweek_entry)
        db.session.commit()
        # Update all users with new teams (example logic)
        users = User.query.all()
        for user in users:
            user.team_choice = None  # Reset team choice
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


@app.route('/registerIOS', methods=['POST'])
def registerIOS():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')

    # Check if the username already exists
    if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
        return jsonify({"msg": "Username or email already used. \n Please choose a different one."}), 401


    # Create a new user
    else:
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash('Account created successfully! Please log in.', 'success')
        return jsonify({"msg": "User successfully registered, please log in."}), 200

@app.route('/createleagueIOS', methods=['POST'])
def createleagueIOS():
    data = request.json
    username = data.get('username')

    league_name = data.get('leaguename')
    password = data.get('password')
    current_user = User.query.filter_by(username=username).first()
    # First, try to find user by username
    current_user = User.query.filter_by(username=username).first()
    # If not found and identifier contains '@', try as email
    if not current_user and "@" in username:
        current_user = User.query.filter_by(email=username).first()
    # Check if the username already exists
    if League.query.filter_by(name = league_name).first():
        return jsonify({"msg": "League name already used. \n Please choose a different one."}), 401


    # Create a new user
    else:
        new_league = League(name=league_name)
        new_league.set_password(password)
        new_league.add_user_id(current_user.id)
        db.session.add(new_league)
        db.session.commit()
        new_league = League.query.filter_by(name=league_name).first()
        current_user.add_league_id(new_league.id)
        db.session.commit()




        flash('Account created successfully! Please log in.', 'success')
        return jsonify({"msg": "League successfully created."}), 200



@app.route('/loginIOS', methods=['POST'])
def loginIOS():
    data = request.json
    identifier = data.get('username')
    password = data.get('password')
    admin = User.query.filter_by(username="admin").first()
    teams = read_current_gameweek_teams()
    teams_new_string = {}

    # First, try to find user by username
    user = User.query.filter_by(username=identifier).first()
    # If not found and identifier contains '@', try as email
    if not user and "@" in identifier:
        user = User.query.filter_by(email=identifier).first()
    
    # No user found
    if not user:
        return jsonify({"msg": "Invalid username"}), 401

    # User found but password is wrong
    if not user.check_password(password):
        return jsonify({"msg": "Invalid password"}), 401

    # Build teams_new_string as before
    if user.doubleup:
        for key, value in teams.items():
            teams_new_string[transform_match_string(key)] = 2 * value
    else:
        for key, value in teams.items():
            teams_new_string[transform_match_string(key)] = value

    # Calculate round as before
    if admin.previous_results is None:
        round = 1
    else:
        if admin.delayed_matches is not None:
            round = len(json.loads(admin.previous_results)) + len(json.loads(admin.delayed_matches)) 
        else:
            round = len(json.loads(admin.previous_results)) + 1

    # Prepare token and response as before
    token = create_access_token(identity=user.username)
    team_choice = transform_match_string(user.team_choice) if user.team_choice else ""
    locked_team_choice = transform_match_string(user.locked_team_choice) if user.locked_team_choice else ""
    presented_team_choice = locked_team_choice if locked_team_choice else team_choice

    gameweek_teams = GameWeekTeams.query.first()
    deadline = str(gameweek_teams.start_time) if gameweek_teams else ""

    return jsonify({
        'access_token': token,
        'username': user.username,
        'score': user.score,
        'gold': user.gold,
        'team_choice': presented_team_choice,
        'round': round,
        'teams': teams_new_string,
        'doubleup': user.doubleup,
        'doubleupsleft': user.doubleupsleft,
        'goal_difference': user.gd,
        'gd_bonus': user.GD_bonus,
        'gd_bonusleft': user.GD_bonus_left,
        'deadline': deadline
    }), 200




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
    # First, try to find user by username
    user = User.query.filter_by(username=username).first()
    # If not found and identifier contains '@', try as email
    if not user and "@" in username:
        user = User.query.filter_by(email=username).first()

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
    if user.doubleup:
        for key,value in teams.items():
            teams_new_string[transform_match_string(key)] = 2*value
    else:
        for key,value in teams.items():
            teams_new_string[transform_match_string(key)] = value
    if admin.previous_results is None:
        round = 1
    else:
        if admin.delayed_matches is not None:
            round = len(json.loads(admin.previous_results)) +len(json.loads(admin.delayed_matches)) 
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

    if locked_team_choice != "":
        presented_team_choice = locked_team_choice
    else:
        presented_team_choice = team_choice
    return jsonify({
        'access_token': "",
        'username': user.username,
        'score': user.score,
        'gold': user.gold,
        'team_choice': presented_team_choice,
        'round': round,
        'teams': teams_new_string, 
        'doubleup':user.doubleup,
        'doubleupsleft':user.doubleupsleft,
        "goal_difference": user.gd,
        'gd_bonus':user.GD_bonus,
        'gd_bonusleft':user.GD_bonus_left
    }), 200




@app.route('/gd_bonusIOS', methods=['POST'])
def gd_bonusIOS():
    data = request.json
    username = data.get('username')
    gd_bonus = data.get('gd_bonus')
    admin = User.query.filter_by(username="admin").first()

    user = User.query.filter_by(username=username).first()
    if not user and "@" in username:
        user = User.query.filter_by(email=username).first()

    if user.GD_bonus_left > 0:
        user.GD_bonus = gd_bonus
    db.session.commit()
        # Get game week teams
    teams = read_current_gameweek_teams()
    teams_new_string = {}
    if user.doubleup:
        for key,value in teams.items():
            teams_new_string[transform_match_string(key)] = 2*value
    else:
        for key,value in teams.items():
            teams_new_string[transform_match_string(key)] = value
    if admin.previous_results is None:
        round = 1
    else:
        if admin.delayed_matches is not None:
            round = len(json.loads(admin.previous_results)) +len(json.loads(admin.delayed_matches)) 
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

    if locked_team_choice != "":
        presented_team_choice = locked_team_choice
    else:
        presented_team_choice = team_choice
    return jsonify({
        'access_token': "",
        'username': user.username,
        'score': user.score,
        'gold': user.gold,
        'team_choice': presented_team_choice,
        'round': round,
        'teams': teams_new_string, 
        'doubleup':user.doubleup,
        'doubleupsleft':user.doubleupsleft,
        "goal_difference": user.gd,
        'gd_bonus':user.GD_bonus,
        'gd_bonusleft':user.GD_bonus_left
    }), 200



@app.route('/doubleupIOS', methods=['POST'])
def doubleupOS():
    data = request.json
    username = data.get('username')
    doubleup = data.get('doubleUp')
    admin = User.query.filter_by(username="admin").first()

    user = User.query.filter_by(username=username).first()
    if not user and "@" in username:
        user = User.query.filter_by(email=username).first()
    if user.doubleupsleft > 0:
        user.doubleup = doubleup
    db.session.commit()
        # Get game week teams
    teams = read_current_gameweek_teams()
    teams_new_string = {}
    if user.doubleup:
        for key,value in teams.items():
            teams_new_string[transform_match_string(key)] = 2*value
    else:
        for key,value in teams.items():
            teams_new_string[transform_match_string(key)] = value
    if admin.previous_results is None:
        round = 1
    else:
        if admin.delayed_matches is not None:
            round = len(json.loads(admin.previous_results)) +len(json.loads(admin.delayed_matches)) 
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

    if locked_team_choice != "":
        presented_team_choice = locked_team_choice
    else:
        presented_team_choice = team_choice
    return jsonify({
        'access_token': "",
        'username': user.username,
        'score': user.score,
        'gold': user.gold,
        'team_choice': presented_team_choice,
        'round': round,
        'teams': teams_new_string, 
        'doubleup':user.doubleup,
        'doubleupsleft':user.doubleupsleft,
        "goal_difference": user.gd,
        'gd_bonus':user.GD_bonus,
        'gd_bonusleft':user.GD_bonus_left
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
        if not user and "@" in username:
            user = User.query.filter_by(email=username).first()
        user_leagues = json.loads(user.league_ids)

        user_leagues_str = [str(League.query.get(id).name)  for id in user_leagues]

        print (user_leagues)
        # Add the global "Worldwide" league
        all_leagues = ["Worldwide"] + user_leagues_str

        # Return the list of league
        return jsonify({"leagues": all_leagues}), 200

    except Exception as e:
        # Handle unexpected errors
        return jsonify({"error": str(e)}), 500

@app.route('/unregisterIOS', methods=['POST'])
def unregisterIOS():
    try:
        data = request.json
        username = data.get("user")

        if not username:
            return jsonify({"message": "Username is required"}), 400

        user = User.query.filter_by(username=username).first()
        if not user and "@" in username:
            user = User.query.filter_by(email=username).first()
        if not user:
            return jsonify({"message": "User not found"}), 404

        # Get the list of league IDs this user belongs to
        league_ids = json.loads(user.league_ids) if user.league_ids else []

        for league_id in league_ids:
            league = League.query.get(league_id)
            if league:
                user_ids = json.loads(league.user_ids) if league.user_ids else []
                if user.id in user_ids:
                    user_ids.remove(user.id)
                    league.user_ids = json.dumps(user_ids)
                    db.session.add(league)  # mark league for update

        # Delete the user
        db.session.delete(user)
        db.session.commit()

        return jsonify({"message": f"User '{username}' successfully unregistered and deleted."}), 200

    except Exception as e:
        app.logger.error(f"Error in unregisterIOS: {e}")
        return jsonify({"message": "An internal error occurred"}), 500

    

@app.route('/get_previous_picksIOS', methods = ['POST'])
def get_previous_picksIOS():
    data = request.json
    username = data.get("user")
    user = User.query.filter_by(username=username).first()
    if not user and "@" in username:
        user = User.query.filter_by(email=username).first()
    previous_results_dict = json.loads(user.previous_results or '{}')
    new_results_dict = {}
    for round, round_dict in previous_results_dict.items():
        new_results_dict[round] = {'team':transform_match_string(round_dict['team']),'score':round_dict['score']}

    return jsonify({"gold":user.gold,"score":user.score,"dictionary":new_results_dict})


@app.route('/get_league_detailsIOS', methods=['POST'])
def get_league_details():
    data = request.json
    league_name = data.get("league_name")


    page = int(data.get("page", 1))
    per_page = 10  # Number of rows per page
    if league_name == "Worldwide":
        users = User.query.order_by(User.score.desc(), User.gold.desc()).all()  # Fetch all users
    else:
        # Fetch league from the database
        league = League.query.filter_by(name=league_name).first()
        if not league:
            return jsonify({"error": "League not found"}), 400

        # Fetch users in the league
        user_ids = json.loads(league.user_ids) if league.user_ids else []
        users = User.query.filter(User.id.in_(user_ids)).order_by(User.score.desc(), User.gold.desc()).all()

    # Prepare the paginated member list
    total_members = len(users)
    total_pages = math.ceil(total_members / per_page)
    start_index = (page - 1) * per_page
    end_index = start_index + per_page

    members = []
    for user in users[start_index:end_index]:
        team_choice = user.locked_team_choice if user.locked_team_choice is not None else ''
        if team_choice != '':
            transformed_team_choice = transform_match_string(team_choice)
            shortened_team_choice = shorten_match_string(transformed_team_choice)
            if user.doubleup:
                shortened_team_choice += '*'
            if user.GD_bonus:
                shortened_team_choice += '+'
        else:
            shortened_team_choice = ''
        members.append({
            "username": user.username,
            "points": round(user.score,1),
            "gold": user.gold,
            "goal_difference": user.gd,
            "locked_team": shortened_team_choice
        })
    return jsonify({
        "members": members,
        "total_pages": total_pages
    })




def transform_match_string(input_string):
    if input_string is None:
        return None

    parts = input_string.split('_', 2)  # e.g., ["Liverpool", "Chelsea", "H"]
    if len(parts) < 2:
        return input_string

    team1 = parts[0]
    team2 = parts[1]
    suffix = parts[2] if len(parts) == 3 else ""

    if suffix == "H":
        # Home emoji after home team, before "vs"
        return f"{team1} 🏠 vs {team2}"
    elif suffix == "A":
        # Away emoji stays at the end
        return f"{team1} 🌍 vs {team2}"
    else:
        return f"{team1} vs {team2}"



def shorten_match_string(input_str):
    home,away = input_str.split(' vs ')
    HorA = input_str[-1]
    try:
        away_new = TEAM_MAPS[away[0:-2]]
        home_new = TEAM_MAPS[home]
    except KeyError:
        away_new = away[0:3]
        home_new = home[0:3]
    return home_new


def inverse_transform_match_string(transformed_string):
    if transformed_string is None:
        return None

    suffix = ""
    cleaned = transformed_string

    # Detect and remove emojis to set suffix
    if '🏠' in cleaned:
        cleaned = cleaned.replace(' 🏠', '')  # strip home emoji
        suffix = '_H'
    elif '🌍' in cleaned:
        cleaned = cleaned.replace(' 🌍', '')
        suffix = '_A'

    # Replace " vs " with first underscore
    inverse_string = cleaned.replace(' vs ', '_', 1)

    return inverse_string + suffix




def send_email(sender_email, sender_password, receiver_email, subject, body):
    # Set up the SMTP server
    smtp_server = "smtp.gmail.com"  # For Gmail
    smtp_port = 587  # Use 465 for SSL, 587 for TLS

    # Create a MIME object
    message = MIMEMultipart()
    message['From'] = sender_email
    message['To'] = receiver_email
    message['Subject'] = subject

    # Add the email body to the MIME message
    message.attach(MIMEText(body, 'plain'))

    # Establish a connection to the Gmail SMTP server
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()  # Upgrade the connection to a secure encrypted SSL/TLS connection

    # Log in to the SMTP server using your email and password
    server.login(sender_email, sender_password)

    # Send the email
    try:
        server.sendmail(sender_email, receiver_email, message.as_string())

        print("Email sent successfully!")
    except:
        print(f"Email to {receiver_email} not sent")
    server.quit()
    return jsonify({"msg": "Password reset email sent."}), 200

@app.route('/fetchNotificationsIOS')
def fetchNotificationsIOS():
    gameweek_teams = GameWeekTeams.query.first()
    start_time = gameweek_teams.start_time
    if (start_time - timedelta(days=30)) > datetime.now():
        start_time = None
    end_time = gameweek_teams.end_time
    next_start_time = gameweek_teams.next_start_time
    return jsonify({
        "start_time":start_time,
        "end_time":end_time,
        "next_start_time":next_start_time
    })

@app.route('/registerLeagueIOS', methods=['POST'])
def register_leagueIOS():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "An internal error occurred"}), 500

        league_name = data.get('league_name')
        league_password = data.get('league_password')
        username = data.get('username')
        current_user = User.query.filter_by(username=username).first()
        if not current_user and "@" in username:
            current_user = User.query.filter_by(email=username).first()
        if not league_name or not league_password:
            return jsonify({"success": False, "message": "League name and password are required"}), 400

        league = League.query.filter_by(name=league_name).first()

        if league and league.check_password(league_password):
            user_ids = json.loads(league.user_ids)
            if current_user.id not in user_ids:
                current_user.add_league_id(league.id)
                league.add_user_id(current_user.id)
                db.session.commit()
                return jsonify({"success": True, "message": "OK"}), 200
            else:
                return jsonify({"success": False, "message": f"User already registered for {league_name}!"}), 200
        else:
            return jsonify({"success": False, "message": "Incorrect league name or password"}), 401

    except Exception as e:
        app.logger.error(f"Error in register_leagueIOS: {e}")
        return jsonify({"success": False, "message": "An internal error occurred"}), 500



@app.route('/send_reset_emailIOS', methods=['POST'])
def send_reset_emailIOS():
    data = request.json
    email = data.get('email')
    user = User.query.filter_by(email=email).first()
    
    if user:
        token = s.dumps(email, salt='password-reset-salt')
        reset_url = url_for('reset_password', token=token, _external=True)
        
        # Send email (example using smtplib)
        send_email('goldenpicks2025@gmail.com', "hihy jobv qtmr zvxl", user.email, "Premier Leauge Predictions Password Reset", f"Password Reset\n\nClick the link to reset your password: {reset_url}")
        
        return jsonify({"msg": "Password reset email sent."}), 200
    else:
        return jsonify({"msg": "Email not found."}), 404

@app.route('/deregister', methods=['GET', 'POST'])
def deregister_web():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return render_template('deregister.html', error="Invalid username or password")

        # Perform the same logic as in unregisterIOS
        league_ids = json.loads(user.league_ids) if user.league_ids else []

        for league_id in league_ids:
            league = League.query.get(league_id)
            if league:
                user_ids = json.loads(league.user_ids) if league.user_ids else []
                if user.id in user_ids:
                    user_ids.remove(user.id)
                    league.user_ids = json.dumps(user_ids)
                    db.session.add(league)

        db.session.delete(user)
        db.session.commit()
        return render_template('deregister.html', success="Account successfully deregistered.")

    return render_template('deregister.html')




@app.route('/team_performanceIOS', methods=['GET'])
def team_performanceIOS():
    all_rows = GameweekStats.query.all()
    team_points = {}
    team_gold = {}

    for row in all_rows:
        gold = json.loads(row.gold)
        points = json.loads(row.points)
        if points == {}:
            continue
        for team, g_val in gold.items():
            team_gold[team] = team_gold.get(team, 0) + g_val
        for team, p_val in points.items():
            team_points[team] = team_points.get(team, 0) + p_val

    # Collect all teams
    all_teams = set(team_gold) | set(team_points)
    results = []
    for team in all_teams:
        gold_sum = team_gold.get(team, 0)
        points_sum = team_points.get(team, 0)
        ratio = points_sum / gold_sum if gold_sum else 0
        results.append({
            'team': team,
            'points': points_sum,
            'gold': gold_sum,
            'ratio': ratio
        })

    # Sort by ratio descending
    results.sort(key=lambda x: x['ratio'], reverse=True)
    return jsonify(results)

# routes_value_picks.py
import ast



def _to_dict(value):
    """Parse dicts stored as JSON or Python-literal strings. Return {} if invalid/empty."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return {}
        try:
            v = json.loads(s)              # proper JSON
            return v if isinstance(v, dict) else {}
        except Exception:
            try:
                v = ast.literal_eval(s)    # handles single quotes
                return v if isinstance(v, dict) else {}
            except Exception:
                return {}
    return {}

def _row_to_teams(row):
    gold = _to_dict(row.gold)
    ex   = _to_dict(row.ex_points)
    out = []
    for team, g in gold.items():
        try:
            g = float(g) if g is not None else 0.0
        except Exception:
            g = 0.0
        try:
            xp = float(ex.get(team, 0.0))
        except Exception:
            xp = 0.0
        out.append({
            "team": team,
            "gold": g,
            "expected_points": xp,
            "value": (xp / g) if g > 0 else 0.0
        })
    out.sort(key=lambda t: t["gold"], reverse=True)
    return out

@app.get("/value_picksIOS")
def value_picksIOS():
    """GET ?gameweek=all|latest|<int>"""
    gw_param = request.args.get("gameweek", "latest").strip().lower()

    try:
        if gw_param == "all":
            rows = GameweekStats.query.order_by(GameweekStats.gameweek.asc()).all()
            data = {}
            for r in rows:
                try:
                    data[str(r.gameweek)] = _row_to_teams(r)
                except Exception as e:
                    print(f"[value_picksIOS] skip gw={r.gameweek} id={r.id} err={e} gold={str(r.gold)[:100]} ex={str(r.ex_points)[:100]}")
            return jsonify({"ok": True, "data": data})

        if gw_param == "latest":
            row = (GameweekStats.query.order_by(GameweekStats.gameweek.desc()).first())
        else:
            row = GameweekStats.query.filter_by(gameweek=int(gw_param)).first()

        if not row:
            return jsonify({"ok": True, "data": {"gameweek": None, "teams": []}})

        try:
            teams = _row_to_teams(row)
        except Exception as e:
            print(f"[value_picksIOS] latest parse err gw={row.gameweek} id={row.id} err={e} gold={str(row.gold)[:100]} ex={str(row.ex_points)[:100]}")
            teams = []  # never 500 here

        return jsonify({"ok": True, "data": {"gameweek": row.gameweek, "teams": teams}})
    except Exception as e:
        print(f"[value_picksIOS] unexpected: {e}")
        return jsonify({"ok": False, "error": "internal error"}), 500


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'GET':
        # Get the token from the query string
        token = request.args.get('token', '')
        
        if not token:
            return jsonify({"msg": "Invalid or missing token."}), 400

        # Decode the token to validate it
        email = s.loads(token, salt='password-reset-salt', max_age=3600)  # Token valid for 1 hour
        user = User.query.filter_by(email=email).first()
        if not user:

            return jsonify({"msg": "Invalid token."}), 400
        
        # Render the reset password page and pass the token to it
        return render_template('reset_password.html', token=token)

    if request.method == 'POST':
        # Get the token and new password from the form
        token = request.form['token']
        new_password = request.form['password']

        # Decode the token to validate it
        email = s.loads(token, salt='password-reset-salt', max_age=3600)  # Token valid for 1 hour
        user = User.query.filter_by(email=email).first()

        if not user:
            return jsonify({"msg": "User not found."}), 400

        # Reset the user's password
        user.set_password(new_password)
        db.session.commit()
        return jsonify({"msg":"Password updated"},200)



def generate_reset_token(user):
    """
    Generates a JWT token for password reset.
    :param user: User object containing user details
    :return: Encoded JWT token
    """
    expiration_time = datetime.utcnow() + timedelta(hours=1)  # Token valid for 1 hour
    payload = {
        "user_id": user.id,  # Include the user's ID
        "email": user.email,  # Include the user's email
        "exp": expiration_time  # Expiration time
    }
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm="HS256")
    return token

if __name__ == '__main__':
    #create_database()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)


