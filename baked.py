# backend.py - FastAPI Backend for Bei Ya Jioni

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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
import os

app = FastAPI(title="Bei Ya Jioni API", version="1.0.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"

# In-memory data storage (use a real database in production)
users_db = {}
tickets_db = []
pending_verifications = []

# Pydantic Models
class User(BaseModel):
    email: EmailStr
    full_name: str
    phone: str
    password: str
    role: str = "buyer"  # buyer, seller, organizer

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Ticket(BaseModel):
    name: str
    event_date: str
    venue: str
    original_price: float
    resale_price: float
    seller_email: EmailStr
    qr_code: Optional[str] = None
    
class TicketVerification(BaseModel):
    ticket_id: int
    status: str  # verified, rejected

# Helper Functions
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def create_token(email: str) -> str:
    payload = {
        "email": email,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Routes
@app.get("/")
async def read_root():
    """Serve the main HTML page"""
    return FileResponse("index.html")

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Bei Ya Jioni API"
    }

@app.post("/api/register")
async def register(user: User):
    """Register a new user"""
    if user.email in users_db:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    users_db[user.email] = {
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "password": hash_password(user.password),
        "role": user.role,
        "id": str(uuid.uuid4())
    }
    
    token = create_token(user.email)
    
    return {
        "message": "Registration successful",
        "token": token,
        "user": {
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role
        }
    }

@app.post("/api/login")
async def login(credentials: UserLogin):
    """Login user"""
    user = users_db.get(credentials.email)
    
    if not user or user["password"] != hash_password(credentials.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(credentials.email)
    
    return {
        "message": "Login successful",
        "token": token,
        "user": {
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"]
        }
    }

@app.get("/api/tickets")
async def get_tickets():
    """Get all available tickets"""
    return {
        "tickets": [t for t in tickets_db if t.get("verified", False)],
        "count": len([t for t in tickets_db if t.get("verified", False)])
    }

@app.post("/api/tickets")
async def create_ticket(ticket: Ticket):
    """Create a new ticket listing"""
    ticket_data = ticket.dict()
    ticket_data["id"] = len(tickets_db) + 1
    ticket_data["qr_code"] = f"QR-{uuid.uuid4().hex[:8].upper()}"
    ticket_data["verified"] = False
    ticket_data["created_at"] = datetime.utcnow().isoformat()
    
    tickets_db.append(ticket_data)
    pending_verifications.append(ticket_data)
    
    return {
        "message": "Ticket submitted for verification",
        "ticket_id": ticket_data["id"],
        "status": "pending"
    }

@app.post("/api/tickets/{ticket_id}/verify")
async def verify_ticket(ticket_id: int, verification: TicketVerification):
    """Verify or reject a ticket (organizer only)"""
    ticket = next((t for t in tickets_db if t["id"] == ticket_id), None)
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    ticket["verified"] = verification.status == "verified"
    ticket["verification_date"] = datetime.utcnow().isoformat()
    
    # Remove from pending
    global pending_verifications
    pending_verifications = [t for t in pending_verifications if t["id"] != ticket_id]
    
    return {
        "message": f"Ticket {verification.status}",
        "ticket_id": ticket_id
    }

@app.get("/api/pending-verifications")
async def get_pending_verifications():
    """Get tickets pending verification (organizer only)"""
    return {
        "pending": pending_verifications,
        "count": len(pending_verifications)
    }

@app.post("/api/tickets/{ticket_id}/purchase")
async def purchase_ticket(ticket_id: int):
    """Purchase a ticket"""
    ticket = next((t for t in tickets_db if t["id"] == ticket_id and t.get("verified")), None)
    
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found or not verified")
    
    # Remove ticket from available listings
    tickets_db.remove(ticket)
    
    # Generate new QR code for buyer
    new_qr = f"SECURE-QR-{uuid.uuid4().hex[:8].upper()}"
    
    return {
        "message": "Purchase successful",
        "ticket": ticket,
        "new_qr_code": new_qr,
        "purchase_date": datetime.utcnow().isoformat()
    }

@app.get("/api/stats")
async def get_stats():
    """Get platform statistics"""
    return {
        "total_tickets": len(tickets_db),
        "verified_tickets": len([t for t in tickets_db if t.get("verified")]),
        "pending_verifications": len(pending_verifications),
        "total_users": len(users_db)
    }

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {"error": "Resource not found"}

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return {"error": "Internal server error"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)