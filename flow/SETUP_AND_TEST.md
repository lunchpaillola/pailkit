# Setup and Test Guide

## Step 1: Create Virtual Environment

```bash
cd /Users/lolaojabowale/pailkit/flow
python3 -m venv venv
```

## Step 2: Activate Virtual Environment

**On macOS/Linux:**
```bash
source venv/bin/activate
```

**On Windows:**
```bash
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt.

## Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 4: Set Up Environment Variables

Create a `.env` file (copy from `env.example`):

```bash
cp env.example .env
```

Then edit `.env` and add at minimum:
```bash
# Required for bot tests
DAILY_API_KEY=your_daily_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Required for server
UNKEY_ROOT_KEY=your_unkey_root_key_here
UNKEY_PAILKIT_SECRET=your_unkey_pailkit_secret_here

# Server URL (for tests)
MEET_BASE_URL=http://localhost:8001
```

## Step 5: Start the Server

**In one terminal window:**
```bash
cd /Users/lolaojabowale/pailkit/flow
source venv/bin/activate  # If not already activated
python main.py
```

The server will start on `http://localhost:8001`

## Step 6: Run Tests (in another terminal)

**In a new terminal window:**
```bash
cd /Users/lolaojabowale/pailkit/flow
source venv/bin/activate  # Activate venv in this terminal too

# Run all bot tests (mocked)
pytest tests/test_one_time_meeting_bot.py -v

# Run integration test (creates real room with bot)
pytest tests/test_one_time_meeting_bot.py::test_create_real_room_with_bot -v -s
```

## Quick Commands Summary

```bash
# Setup (one time)
cd /Users/lolaojabowale/pailkit/flow
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp env.example .env
# Edit .env with your API keys

# Start server (Terminal 1)
cd /Users/lolaojabowale/pailkit/flow
source venv/bin/activate
python main.py

# Run tests (Terminal 2)
cd /Users/lolaojabowale/pailkit/flow
source venv/bin/activate
pytest tests/test_one_time_meeting_bot.py -v -s
```
