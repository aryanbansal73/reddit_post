import os
from dotenv import load_dotenv
from google.cloud import texttospeech

# Load environment variables from .env file
load_dotenv()

# Set the Google Cloud credentials environment variable
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'tts_key.json'

# Initialize the Google Cloud Text-to-Speech client
client = texttospeech.TextToSpeechClient()

def synth_speech(text, output_file):
    # Set the text input to be synthesized
    synthesis_input = texttospeech.SynthesisInput(text=text)
    
    # Build the voice request, select the language code and the voice name
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",name = "en-US-Standard-J"
    )
    
    # Select the type of audio file you want returned
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16 # LINEAR16 is WAV format
    )
    
    # Perform the text-to-speech request on the text input with the selected
    # voice parameters and audio file type
    response = client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )
    
    # The response's audio_content is binary
    with open(output_file, "wb") as out:
        # Write the response to the output file
        out.write(response.audio_content)
        print('Audio content written to file "{}"'.format(output_file))
    
    return True

# Example usage
if __name__ == "__main__":
    text = "My name is Saksham Bansal. I am from Talwara, Punjab. I studied engineering from IIT Ropar."
    output_file = "output.wav"
    success = synth_speech(text, output_file)
    if success:
        print("Speech synthesis succeeded.")
    else:
        print("Speech synthesis failed.")
