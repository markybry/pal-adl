# 🔐 Password Protection Setup

Your dashboard is now password-protected!

## 🚀 Quick Start

**Default Credentials:**
- Password: `admin123`

⚠️ **Change this immediately for production use!**

## 🔧 Setting Your Own Password

### Step 1: Generate Password Hash
```bash
python generate_password.py
```

### Step 2: Create Secrets File
```bash
mkdir .streamlit
# Create .streamlit/secrets.toml with your password hash
```

### Step 3: Add Password Hash
Edit `.streamlit/secrets.toml`:
```toml
password_hash = "your_generated_hash_here"
```

### Step 4: Restart Dashboard
```bash
python -m streamlit run dashboard.py
```

## 🔒 Security Features

✅ **Password hashing** - Passwords never stored in plain text  
✅ **Session-based auth** - Stays logged in during session  
✅ **Logout button** - Users can securely logout  
✅ **Secrets management** - Uses Streamlit's secrets system  
✅ **Git-safe** - secrets.toml automatically ignored  

## 📝 For Team Deployment

### Option 1: Shared Password
- Use `generate_password.py` to create one hash
- Share the password (not the hash) with your team
- Everyone uses the same login

### Option 2: Multiple Users (Advanced)
For multiple users with different passwords, you'll need:
- Install `streamlit-authenticator` library
- Configure with username/password combinations
- See: https://github.com/mkhorasani/Streamlit-Authenticator

## ⚠️ Important Security Notes

1. **Never commit** `.streamlit/secrets.toml` to git (already in .gitignore)
2. **Change default password** before deploying
3. **Use strong passwords** (8+ characters, mixed case, numbers, symbols)
4. **HTTPS recommended** for production deployments
5. **Additional layers**: Consider VPN/IP restrictions for extra security

## 🌐 Deploying with Password Protection

### Streamlit Cloud
Add your password hash in the Streamlit Cloud dashboard:
1. Go to App Settings → Secrets
2. Add: `password_hash = "your_hash"`

### Docker
Use environment variables:
```dockerfile
ENV STREAMLIT_PASSWORD_HASH="your_hash"
```

Update dashboard.py to read from env vars if needed.

## 🆘 Forgot Password?

**Local deployment:**
1. Edit `.streamlit/secrets.toml`
2. Run `python generate_password.py` with new password
3. Replace the hash
4. Restart app

**Production:**
- Access server/cloud platform
- Update secrets configuration
- Redeploy app
