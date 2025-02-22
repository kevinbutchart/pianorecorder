#!/usr/bin/env python3
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect, Form, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import FileResponse
from jinja2 import Environment, FileSystemLoader
import subprocess
from midirecordingsdb import MidiRecordingsDB
from midiplayer import MidiPlayer
from metronome import Metronome
from connectionmanager import ConnectionManager
from pathlib import Path
from player_client import MidiPlayClient
import asyncio
import uvicorn
import json
import tempfile
import queue
import base64
import tempfile

from os.path import dirname, join

current_dir = dirname(__file__)
template_dir = join(current_dir, 'templates')

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory=template_dir)
j2_env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True)
db = MidiRecordingsDB()
#midirecorder = MidiRecorder(db)
metronome = Metronome()

@app.on_event('startup')
async def app_startup():
    print("starting")

@app.on_event('shutdown')
async def app_shutdown():
    print("in app shutdown")

@app.get("/", response_class=HTMLResponse)
async def read_item(request: Request):
    recs = db.get_recording_sessions(limit=150)
    return templates.TemplateResponse("main.html", {"request" : request, "recordings": recs})

@app.get("/recordings", response_class=HTMLResponse)
async def read_item(request: Request, search = ""):
    recs = db.get_recording_sessions(limit=150, search=search)
    return templates.TemplateResponse("recordings.html", {"request" : request, "recordings": recs})

@app.get("/choosetags", response_class=HTMLResponse)
async def read_item(request: Request):
    tags = db.get_tags()
    return templates.TemplateResponse("choosetags.html", {"request" : request, "tags": tags})

@app.get("/rhythm", response_class=HTMLResponse)
async def get_rhythm(request: Request):
    settings = db.get_metronome_settings()
    loops = { 1 : db.get_loops(1), 2: db.get_loops(2), 3: db.get_loops(3), 4: db.get_loops(4)}
    return templates.TemplateResponse("rhythm.html", {"request" : request, "settings" : settings, "loops" : loops})

@app.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    return templates.TemplateResponse("settings.html", {"request" : request})

@app.get("/cer")
async def certificate(request: Request):
    return FileResponse('static/ca.crt', media_type='application/octet-stream',filename='ca.crt')

@app.get("/serviceworker.js")
async def serviceworker(request: Request):
    return FileResponse('static/serviceworker.js')

def midi_to_audio(infile, outfile):
    subprocess.call(['fluidsynth', '-ni', '/sf/yamahac5.sf3', infile, '-F', outfile, '-r', '44100', '-T', 'oga', '-g', '0.5'])


@app.get("/recording/{id}", response_class=HTMLResponse)
async def get_recording(request: Request, background_tasks: BackgroundTasks, id):
    rec = db.get_recording(id)
    tags = db.get_tags()
    return templates.TemplateResponse("recording.html", {"request" : request, "rec" : rec, "tags" : tags})

manager = ConnectionManager()

class CommandRunner():

    def __init__(self):
        self.commands = { "play" : self.play,
                    "stop" : self.stop,
                    "start_metronome" : self.start_metronome,
                    "update_metronome" : self.update_metronome,
                    "stop_metronome" : self.stop_metronome,
                    "set_title" : self.set_title,
                    "add_tag" : self.add_tag,
                    "delete_tag" : self.delete_tag,
                    "set_favourite" : self.set_favourite,
                    "create_synth" : self.create_synth
                    }

    def run(self, message):
        cmd = self.commands[ message['command'] ]
        if cmd is not None:
            cmd(message)

    def play(self, message):
        print(message, flush=True)
        id = message['id']
        MidiPlayClient.play_midi(id)

    def add_tag(self, message):
        id = message['id']
        tag_id = message['tag_id']
        db.add_tag(id, tag_id)

    def delete_tag(self, message):
        id = message['id']
        tag_id = message['tag_id']
        db.delete_tag(id, tag_id)

    def stop(self, message):
        MidiPlayClient.stop_midi()

    def update_metronome(self, message):
        db.set_metronome_settings(message)
        MidiPlayClient.update_metronome()

    def start_metronome(self, message):
        MidiPlayClient.start_metronome()

    def stop_metronome(self, message):
        MidiPlayClient.stop_metronome()

    def set_title(self, message):
        id = message['id']
        title = message['title']
        rec = db.get_recording(id)
        print (id)
        print (rec)
        print(title)
        rec.title = title
        db.commit()

    def set_favourite(self, message):
        id = message['id']
        favourite = message['favourite']

    def create_synth(self, message):
        id = message['id']
        rec = db.get_recording(id)
        print("rec received")
        with open("/tmp/input.mid", "wb") as f:
            print("file opened")
            b = base64.b64decode(rec['data'])
            f.write(b)
        print("file written")
        midi_to_audio("/tmp/input.mid", "/tmp/output.ogg")
        print("converted")
        with open("/tmp/output.ogg") as resfile:
            res = resfile.read()
            print(res)

async def consumer_handler(websocket):
    cmd_runner = CommandRunner()
    while True:
        try:
            message = await websocket.receive_text()
            message = json.loads(message)
            cmd_runner.run(message)
        except WebSocketDisconnect:
            break
        except Exception as e:
            print(e)

async def producer_handler(websocket):
    while True:
        msg = await msg_queue.get()
        msg_content = json.loads(msg)
        print(msg_content)
        if msg_content['msg'] == 'new_recording':
            print('new_rec_received')
            cmd = { 'command' : 'reload' }
            cmdstr = json.dumps(cmd)
            await websocket.send_text(cmdstr)

@app.websocket("/main")
async def websocket_main(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        global msg_queue
        msg_queue = asyncio.Queue()
        consumer_task = asyncio.ensure_future(
            consumer_handler(websocket))
        producer_task = asyncio.ensure_future(
            producer_handler(websocket))
        done, pending = await asyncio.wait(
            [consumer_task, producer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        manager.disconnect(websocket)

    print("Disconnecting socket")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
