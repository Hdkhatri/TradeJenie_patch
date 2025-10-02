import requests
import json

# Harshil telegram bot token
#TOKEN = '8265133867:AAHHPOOnHu5n_wWoXfNYHGvyyBNA4_6ztxY'

#harshil telegram bot chat_id
#CHAT_ID = 8016061002  # replace with your actual chat_id



# url = f'https://api.telegram.org/bot{TOKEN}/getUpdates'
# res = requests.get(url)
# print(json.dumps(res.json(), indent=4))




def send_telegram_message(message, CHAT_ID, TOKEN):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    data = {
        'chat_id': CHAT_ID,
        'text': message
    }
    response = requests.post(url, data=data)
    

if __name__ == "__main__":
    message = 'test message from HDK script'
    send_telegram_message(message)