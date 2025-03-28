const recordButton = document.getElementById('record');
const stopButton = document.getElementById('stop');
const timerDisplay = document.getElementById('timer');
const audioList = document.getElementById('audioList');
const errorMessage = document.getElementById('errorMessage');

let mediaRecorder;
let audioChunks = [];
let startTime;
let timerInterval;

function displayErrorMessage(msg) {
  errorMessage.textContent = msg;
}

// Start Recording
recordButton.addEventListener('click', async () => {
  try {
    console.log("[INFO] Requesting microphone access...");
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    audioChunks = [];
    mediaRecorder.ondataavailable = event => {
      audioChunks.push(event.data);
    };
    mediaRecorder.start();
    startTime = Date.now();
    timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      timerDisplay.textContent = `Recording: ${formatTime(elapsed)}`;
    }, 1000);
    recordButton.disabled = true;
    stopButton.disabled = false;
    timerDisplay.textContent = "Recording...";
    console.log("[INFO] Recording started...");
  } catch (error) {
    console.error('[ERROR] Microphone access denied:', error);
    displayErrorMessage('Microphone access denied. Please enable permissions.');
  }
});

// Stop Recording & Upload
stopButton.addEventListener('click', () => {
  if (!mediaRecorder) {
    console.error("[ERROR] No active mediaRecorder found.");
    return;
  }
  mediaRecorder.stop();
  clearInterval(timerInterval);
  timerDisplay.textContent = "Processing...";
  mediaRecorder.onstop = async () => {
    console.log("[INFO] Recording stopped. Preparing file for upload...");
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('audio_data', audioBlob, 'recorded_audio.webm');
    try {
      const response = await fetch('/upload', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.error) {
        displayErrorMessage(`Upload Error: ${data.error}`);
        return;
      }
      if (data.processed_file) {
        console.log("[INFO] Upload successful:", data.processed_file);
        // Create a new list item with the new MP3 file and sentiment file link
        const newAudioItem = document.createElement('li');
        newAudioItem.innerHTML = `
          <audio controls>
            <source src="/uploads/${data.processed_file}" type="audio/mp3">
            Your browser does not support the audio element.
          </audio>
          <br><strong>${data.processed_file}</strong>
          <p>
            <a href="/uploads/${data.sentiment_analysis_file}" target="_blank">
              Download Sentiment Analysis
            </a>
          </p>
        `;
        audioList.appendChild(newAudioItem);
        timerDisplay.textContent = "Recording saved!";
      } else {
        displayErrorMessage("Upload failed. No file info from server.");
      }
    } catch (err) {
      console.error('[ERROR] Upload failed:', err);
      displayErrorMessage('Failed to upload the audio.');
    }
  };
  recordButton.disabled = false;
  stopButton.disabled = true;
});

// Format Time
function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}
