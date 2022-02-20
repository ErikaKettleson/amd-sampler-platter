#!/usr/bin/env python

import os
import re

from dotenv import load_dotenv
from faker import Faker
from flask import Flask, Response, jsonify, redirect, request
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import Dial, VoiceResponse
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

load_dotenv()

app = Flask(__name__)
fake = Faker()
alphanumeric_only = re.compile("[\W_]+")
phone_pattern = re.compile(r"^[\d\+\-\(\) ]+$")

twilio_number = os.environ.get("TWILIO_CALLER_ID")
client = Client(os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN"))


# Store the most recently created identity in memory for routing calls
IDENTITY = {"identity": ""}


@app.route("/")
def index():
    return app.send_static_file("index.html")



@app.route("/token", methods=["GET"])
def token():
    # get credentials for environment variables
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    application_sid = os.environ["TWILIO_TWIML_APP_SID"]
    api_key = os.environ["API_KEY"]
    api_secret = os.environ["API_SECRET"]

    # Generate a random user name and store it
    identity = alphanumeric_only.sub("", fake.user_name())
    IDENTITY["identity"] = identity

    # Create access token with credentials
    token = AccessToken(account_sid, api_key, api_secret, identity=identity)

    # Create a Voice grant and add to token
    voice_grant = VoiceGrant(
        outgoing_application_sid=application_sid,
        incoming_allow=True,
    )
    token.add_grant(voice_grant)

    # Return token info as JSON
    token = token.to_jwt()

    # Return token info as JSON
    return jsonify(identity=identity, token=token)


@app.route("/amd", methods=["POST"])
def amd():
    inbound_sid = request.values.get('InboundSid', None)
    outbound_sid = request.values.get('CallSid', None)
    inbound_caller_id = request.values.get('InboundCallerId', '')
    call_status = request.values.get('CallStatus', '')
    answered_by = request.values.get('AnsweredBy', '')
    
    # twiml = '<Response><Say>Hello, just a moment please.</Say></Response>/'
    
    import ipdb;
    ipdb;

    resp = VoiceResponse()

    if answered_by == "human":
        # this announces to the pstn number - also announce to conference? connect to conference
        resp.say('Standard AMD call answered by a human. Goodbye...')
    else:
        resp.say('Standard AMD call went to voicemail. Goodbye...')

    # need to connect call if human
    
    return Response(str(resp), mimetype="text/xml")


# @app.route("/voice", methods=["POST"])
# def voice():
#     resp = VoiceResponse()
#     if request.form.get("To") == twilio_number:
#         # Receiving an incoming call to our Twilio number
#         dial = Dial()
#         # Route to the most recently created client based on the identity stored in the session
#         dial.client(IDENTITY["identity"])
#         resp.append(dial)
#     elif request.form.get("To"):
#         # Placing an outbound call from the Twilio client
#         dial = Dial(caller_id=twilio_number)
#         # wrap the phone number or client name in the appropriate TwiML verb
#         # by checking if the number given has only digits and format symbols
#         if phone_pattern.match(request.form["To"]):
#             dial.number(request.form["To"])
#         else:
#             dial.client(request.form["To"])
#         resp.append(dial)
#     else:
#         resp.say("Thanks for calling!")

#     return Response(str(resp), mimetype="text/xml")

@app.route("/voice", methods=["POST"])
def voice():
    resp = VoiceResponse()
    if request.form.get("To") == twilio_number:
        # Receiving an incoming call to our Twilio number
        dial = Dial()
        # Route to the most recently created client based on the identity stored in the session
        dial.client(IDENTITY["identity"])
        resp.append(dial)
    elif request.form.get("To"):

        # Placing an outbound call from the Twilio client
        dial = Dial(caller_id=twilio_number)
        # wrap the phone number or client name in the appropriate TwiML verb
        # by checking if the number given has only digits and format symbols
        if phone_pattern.match(request.form["To"]):
            inbound_sid = request.form["CallSid"]
            url = request.form["url"]
            machine_detection = request.form["machineDetection"]
            # park inbound leg in a conference
            dial.conference(
                'My test conference',
                end_conference_on_exit=True
            )
            # make outbound API with AMD 
            try:
                call = client.calls.create(
                    to=request.form.get("To"),
                    from_=twilio_number,
                    url=url,
                    machine_detection=machine_detection
                )
            except TwilioRestException as ex:
                abort(500, ex.msg)

        else:
            dial.client(request.form["To"])
        resp.append(dial)
    else:
        resp.say("Thanks for calling!")

    return Response(str(resp), mimetype="text/xml")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
