# Discord-Message-Summarizer

Scrapes messages from any specific person and use a DL Processing to summarize anything related to the identity of the user.

## Disclaimer

This project is only intended for educational, research, and information gathering testing purposes.
Any act of misuse for harmful gain of this software for activities related to unauthorized surveillance, harassment, invasion of privacy, or doxxing is highly prohibited and may get your Discord account flagged.
The contributors and maintainers of this project are **not responsible** for any misuse, damage, legal consequences, or unethical activities caused by the use of this software. You (users) are solely responsible for ensuring that the usage of this program complies with applicable laws and regulations.

## Installation

1. Run `git clone https://github.com/3oFiz4/Discord-Message-Summarizer`
2. Run `pip install -r requirements.txt`
3. Go to `config.py`, there set your target, including author, channel.
4. Create a file named `.env` and add `DISCORD_TOKEN="<ur_discord_token>"`
5. Do `python main.py`
6. Wait, until the CLI says your `.csv` file is done. Check on `output/`.
7. (coming soon)

## Features

- [x] Message Scraper
- [ ] CLI Arguments Parser
- [ ] Multi-Platform Scraper
- [ ] Processor (DeepLearning Process)
- [x] Colored Terminal

## Contributor

- 3oFiz4 (Owner, Conceptor, System Architecture Designer)
