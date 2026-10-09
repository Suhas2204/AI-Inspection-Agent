"""redlining.speech: the input sources that turn a voice into a Read.

Two of them, same interface, same output: audio_input records from a
microphone and transcribes locally, streamlit_input transcribes a clip the
page has already recorded. KeyboardInput and ScriptedInput are the other two
implementations of that interface and live in session.py, next to the loop
that walks the checklist with them.

Not io/: that shadows the standard library's io module for anything that
puts this directory on sys.path, which is how core/types.py broke a direct
`python src/redlining/core/adjudicate.py` before it became core/reads.py.

Both modules are re-exported at their old top-level paths.
"""
