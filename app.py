#!/usr/bin/env python

import os
import re

from dotenv import load_dotenv
from faker import Faker
from flask import Flask, Response, jsonify, redirect, request, render_template, session
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import Dial, VoiceResponse
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from flask_session import Session

load_dotenv()

app = Flask(__name__,template_folder='templates')
SESSION_TYPE = 'filesystem'
PERMANENT_SESSION_LIFETIME = 30
app.config.from_object(__name__)
Session(app)


fake = Faker()
alphanumeric_only = re.compile("[\W_]+")
phone_pattern = re.compile(r"^[\d\+\-\(\) ]+$")

twilio_number = os.environ.get("TWILIO_CALLER_ID")
client = Client(os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN"))


# Store the most recently created identity in memory for routing calls
IDENTITY = {"identity": ""}


@app.route("/")
def index():
    return render_template("index.html")


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
    machine_detection_duration = request.values.get('MachineDetectionDuration', '')
        
    with open("answered_by.txt", "w") as outfile:
        outfile.writelines([answered_by, '\n'])
        outfile.writelines([machine_detection_duration, '\n'])

        print('writing answered by to txt file: ', answered_by, machine_detection_duration)


    resp = VoiceResponse()
    print("request.values: ", request.values)
    with open("pstn_leg_sid.txt", "r") as infile:
        call_sid = infile.readlines()[0].rstrip()

        print("in bridge_conference - call sid: ", call_sid)

        file = open("pstn_leg_sid.txt","w")
        file.close() 

    if answered_by == "human":
        # connect pstn leg to conference        
        call = client.calls(call_sid).update(twiml='<Response>"Standard AMD call answered by a human. Bridging now!"<Say></Say><Dial><Conference>AMDConference</Conference></Dial></Response>')

    else:
        resp.say('Standard AMD detected this is not a human. Goodbye...')
        # hangup conference here as well
        # hangupIncomingCall(call_sid)
    

    # would be nice to auto hang up conference 
    return str(resp)

@app.route("/get_answered_by", methods=["GET"])
def get_answered_by():
    
    with open("answered_by.txt", "r") as infile:
        answered_by = infile.readline().rstrip()
        machine_detection_duration = infile.readline().rstrip()
        print("in get answered by!!: ", answered_by, machine_detection_duration)    

    open("answered_by.txt", "w").close()

    return jsonify([answered_by, machine_detection_duration])


@app.route("/bridge_conference", methods=["GET", "POST"])
def bridge_conference():
    # add call leg to conference so we can hear it
    # resp = VoiceResponse()
    # dial = Dial()
    # dial.conference('AMDConference')
    # resp.append(dial)
    # import ipdb; ipdb.set_trace()

    with open("pstn_leg_sid.txt", "r") as infile:
        call_sid = infile.readlines()[0].rstrip()
    
    print("in bridge_conference - call sid: ", call_sid)

    file = open("pstn_leg_sid.txt","w")
    file.close() 

    call = client.calls(call_sid).update(twiml='<Response><Dial><Conference>AMDConference</Conference></Dial></Response>')

    return call_sid


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
            machine_detection_timeout = request.form["machineDetectionTimeout"]
            machine_detection_speech_threshold = request.form["machineDetectionSpeechThreshold"]
            machine_detection_speech_end_threshold = request.form["machineDetectionSpeechEndThreshold"]
            machine_detection_silence_timeout = request.form["machineDetectionSilenceTimeout"]
            # park inbound leg in a conference
            dial.conference(
                'AMDConference',
                end_conference_on_exit=True
            )
            # make outbound API with AMD 
            try:
                call = client.calls.create(
                    to=request.form.get("To"),
                    from_=twilio_number,
                    url=url,
                    machine_detection=machine_detection,
                    machine_detection_timeout=machine_detection_timeout,
                    machine_detection_speech_threshold=machine_detection_speech_threshold,
                    machine_detection_speech_end_threshold=machine_detection_speech_end_threshold,
                    machine_detection_silence_timeout=machine_detection_silence_timeout
                )
                
                call_sid = call.sid
                with open("pstn_leg_sid.txt", "w") as outfile:
                    outfile.writelines([call_sid, '\n'])
                    print('wrote to pstn_leg_sid: ', call_sid)

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
