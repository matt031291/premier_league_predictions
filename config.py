import os

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL','postgresql://master:master@database-premier-league-predictions.cdeacqwaa9qe.eu-north-1.rds.amazonaws.com:5432/test')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv('SECRET_KEY', 'you-will-never-guess')