"""
Test script to check available Gemini models with your API key
"""
import google.generativeai as genai

# Configure with your API key
GEMINI_API_KEY = "AIzaSyD3IaCa-CJAHLCDWlOpNDK8SJ4b6-Q0n9s"
genai.configure(api_key=GEMINI_API_KEY)

print("=" * 60)
print("CHECKING AVAILABLE GEMINI MODELS")
print("=" * 60)

# List all available models
try:
    print("\n📋 Listing all available models...\n")
    for model in genai.list_models():
        if 'generateContent' in model.supported_generation_methods:
            print(f"✅ Model: {model.name}")
            print(f"   Display Name: {model.display_name}")
            print(f"   Description: {model.description[:100]}...")
            print(f"   Supported methods: {model.supported_generation_methods}")
            print("-" * 60)
except Exception as e:
    print(f"❌ Error listing models: {e}")

print("\n" + "=" * 60)
print("TESTING SPECIFIC MODEL NAMES")
print("=" * 60)

# Test common model names
test_models = [
    'gemini-pro',
    'gemini-1.5-pro',
    'gemini-1.5-flash',
    'gemini-2.0-flash',
    'gemini-2.5-flash',
    'models/gemini-pro',
    'models/gemini-1.5-pro',
]

for model_name in test_models:
    print(f"\n🧪 Testing: {model_name}")
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content("Say 'Hello, I am working!'")
        print(f"   ✅ SUCCESS! Response: {response.text[:50]}")
    except Exception as e:
        print(f"   ❌ FAILED: {str(e)[:100]}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
