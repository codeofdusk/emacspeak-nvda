import functools
import socketserver
import threading

import speech
import versionInfo

from collections import deque


class Emacspeaker(socketserver.TCPServer):
    "An NVDA Emacspeak server."

    def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True):
        "Initializes the speech server."
        self._state = {}  # TTS state
        self._header = []  # Speech commands to send before speaking
        self._queue = deque()  # TTS queue
        self._cmdMap = {
            "tts_saytext": functools.partial(
                speech.speak, priority=speech.priorities.SpeechPriority.NOW
            ),  # todo: handle morpheme boundaries as described in the spec
            "q": self.q,
            "d": self.d,
            "l": self.l,
            "tts_pause": self.pause,
            "tts_resume": self.resume,
            "s": self.s,
            "t": self.t,
            "tts_set_speech_rate": self.setRate,
            "tts_set_character_scale": self.setCharacterScale,
            "version": self.version,
            "tts_reset": self.reset,
            # TODO: allow the punctuation level to be changed by the user (I.E. don't depend on NVDA)
        }
        socketserver.TCPServer.__init__(self, server_address, RequestHandlerClass)

    def parseCommand(self, cmd):
        "Parses an Emacspeak command string and calls the appropriate method for handling."
        # Strip whitespace and tokenize
        t = cmd.strip().split(" ")
        if len(t) < 2:
            t.append("")  # No args, so add an empty args token.
        # Get rid of braces
        if t[1].startswith("{"):
            t[1] = t[1][1:]
        if t[-1].endswith("}"):
            t[-1] = t[-1][:-1:]
        # Call the appropriate method if possible
        if t[0] in self._cmdMap:
            self._cmdMap[t[0]](t[1:])

    def q(self, args):
        "Enqueues text for speaking."
        text = " ".join(args)
        self._queue.extend([text, speech.EndUtteranceCommand()])

    def d(self, args):
        "Dispatches our internal queue to NVDA's speech framework."
        res = []
        res.extend(self._header)  # Add speech params
        res.extend(self._queue)  # Add queued speech
        speech.speak(res, priority=speech.priorities.SpeechPriority.NOW)
        self._queue.clear()

    def l(self, args):
        "Speak a single character (or set of characters) immediately."
        res = []
        res.extend(self._header)
        if "character_scale" in self._state:
            res.append(speech.RateCommand(multiplier=self._state["character_scale"]))
        res.extend(list(speech.getSpellingSpeech("".join(args))))
        speech.cancelSpeech()  # Flush NVDA's speech queue
        speech.speak(res, priority=speech.priorities.SpeechPriority.NOW)

    def pause(self, args):
        "Pause speech."
        speech.pauseSpeech(True)

    def resume(self, args):
        "Resume speech."
        speech.pauseSpeech(False)

    def s(self, args):
        "Stop speech; flushes NVDA and internal queues."
        speech.cancelSpeech()
        self._queue.clear()

    def t(self, args):
        "Queues a tone of the given length and frequency."
        if len(args) != 2:  # Wrong number of arguments
            return
        self._queue.append(speech.BeepCommand(float(args[0]), int(args[1])))

    def setRate(self, args):
        "Sets the speech rate to the absolute value given."
        value = int(args[0])
        self._state["rate_offset"] = value - speech.RateCommand().newValue
        self._buildHeader()

    def setCharacterScale(self, args):
        "Sets the character scale factor to the multiplier given."
        self._state["character_scale"] = float(args[0])

    def version(self, args):
        "Speaks the version of NVDA on which this server runs."
        res = self._header
        res.append("NVDA " + versionInfo.version)
        speech.speak(res, priority=speech.priorities.SpeechPriority.NOW)

    def reset(self):
        "Clears TTS state and rebuilds headers."
        self._state = {}
        self._buildHeader()

    def _buildHeader(self):
        "Builds the header of TTS commands when state is updated."
        self._header = []  # Clear out any previous headers.
        if "rate_offset" in self._state:
            self._header.append(speech.RateCommand(self._state["rate_offset"]))


class TCPHandler(socketserver.StreamRequestHandler):
    "Handles incoming TCP data from Emacs and forwards it to the Emacspeaker instance."

    def handle(self):
        for line in self.rfile:
            self.server.parseCommand(line.decode("utf-8").strip())


def start():
    "Starts the Emacspeak TCP server."
    server = Emacspeaker(("localhost", 6832), TCPHandler)
    serverthread = threading.Thread(target=server.serve_forever)
    serverthread.start()


# TODO: wrap this logic in an NVDA plugin of some kind.
