import hashlib

print("🔐 Password Hash Generator for CQC Dashboard\n")
print("This tool generates a secure hash for your dashboard password.")
print("-" * 60)

password = input("\nEnter your desired password: ")
confirm = input("Confirm password: ")

if password != confirm:
    print("\n❌ Passwords don't match! Please try again.")
    exit(1)

if len(password) < 8:
    print("\n⚠️  Warning: Password is less than 8 characters. Consider using a stronger password.")

# Generate hash
password_hash = hashlib.sha256(password.encode()).hexdigest()

print("\n✅ Password hash generated successfully!")
print("-" * 60)
print(f"\nYour password hash:\n{password_hash}")
print("\n" + "-" * 60)
print("\nNext steps:")
print("1. Create folder: .streamlit/")
print("2. Create file: .streamlit/secrets.toml")
print("3. Add this line to the file:")
print(f'\n   password_hash = "{password_hash}"')
print("\n4. Restart your Streamlit app")
print("\n⚠️  IMPORTANT: Keep this hash private and never commit secrets.toml to git!")
