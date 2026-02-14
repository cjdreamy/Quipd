# backend.py - FastAPI Backend for Bei Ya Jioni

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import hashlib
import jwt
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import uuid
import random
import string

app = FastAPI(title="Bei Ya Jioni API", version="1.0.0")

# CORS Configuration
app.add