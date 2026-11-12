# JobSearchBot

Telegram bot that searches vacancies on Work.ua by the text you send.

## Run locally
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then put your BOT_TOKEN into .env
python bot.py
```

## Tests
```bash
python -m unittest discover tests
```
