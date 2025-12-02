from sqlalchemy import create_engine
DATABASE_URL = "mysql+pymysql://root:q1w2e3@localhost:3306/reach_you"
engine = create_engine(DATABASE_URL)