# leafwind springegg robot

## Installation
After you have cloned this repository, use pipenv to install packages

```sh
$ pipenv install --dev
```

## Usage
To run the chatbot, you will need to provide an OAuth access token with the chat_login scope.  You can reference an authentication sample to accomplish this, or simply use the [Twitch Chat OAuth Password Generator](http://twitchapps.com/tmi/).

The `run.sh` contains the following shell to run the process:
```sh
pipenv run python chatbot.py <username> <token>
```
* Username - The username of the chatbot
* Token - Your OAuth Token, load from `.env` file


### Get IRC oauth token (for IRC chat and commands)

Use [Twitch Chat OAuth Password Generator](https://twitchapps.com/tmi/) in [Chatbots & IRC Guide](https://dev.twitch.tv/docs/irc/guide#scopes-for-irc-commands)

### Get app access token (for getting information from stream, chat, user, ..., etc.)

Use [The OAuth client credentials flow](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth#oauth-client-credentials-flow) to handle our server-to-server API requests.

Get token by sending client ID and secret, which can be retrieved from: [Twitch Developer Console](https://dev.twitch.tv/console/apps)

```
pipenv run python get_twitch_app_token.py
```

## Dev

### Run lint

```shell
$ pipenv run lint
```

### Run test

```shell
$ pipenv run test
```