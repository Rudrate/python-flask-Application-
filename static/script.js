// Unique naming to ensure uniqueness
const recordBtn = document.getElementById('recordBtn');
const stopBtn = document.getElementById('stopBtn');
const timerEl = document.getElementById('timerDisplay');
const answerSection = document.getElementById('answerSection');
const errorEl = document.getElementById('errorDisplay');

let recorder;
let audioData = [];
let recordStartTime;
let recordInterval;

function displayError(msg) {
  errorEl.textContent = msg;
}

recordBtn.addEventListener('click', async () => {
  try {
    console.log("[INFO] Requesting microphone access...");
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    audioData = [];
    recorder.ondataavailable = event => {
      audioData.push(event.data);
    };
    recorder.start();
    recordStartTime = Date.now();
    recordInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - recordStartTime) / 1000);
      timerEl.textContent = `Recording: ${formatTime(elapsed)}`;
    }, 1000);
    recordBtn.disabled = true;
    stopBtn.disabled = false;
    timerEl.textContent = "Recording in progress...";
    console.log("[INFO] Recording started...");
  } catch (error) {
    console.error("[ERROR] Microphone access denied:", error);
    displayError("Microphone access denied. Please enable permissions.");
  }
});

stopBtn.addEventListener('click', () => {
  if (!recorder) {
    console.error("[ERROR] No active recorder found.");
    return;
  }
  recorder.stop();
  clearInterval(recordInterval);
  timerEl.textContent = "Processing...";
  recorder.onstop = async () => {
    console.log("[INFO] Recording stopped. Preparing upload...");
    const blob = new Blob(audioData, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('audio_data', blob, 'user_query.webm');
    try {
      const response = await fetch('/ask_book', { method: 'POST', body: formData });
      const result = await response.json();
      if (result.error) {
        displayError(`Upload Error: ${result.error}`);
        return;
      }
      if (result.tts_file) {
        // Append the live response to the answer section
        const li = document.createElement('li');
        li.innerHTML = `
          <p><strong>Question:</strong> ${result.transcribed_question}</p>
          <p><strong>Answer:</strong> ${result.answer_text}</p>
          <audio controls>
            <source src="/uploads/${result.tts_file}" type="audio/mp3">
            Your browser does not support audio.
          </audio>
        `;
        answerSection.appendChild(li);
        // Optionally, update the results panels directly
        // Assuming history panels with IDs "historyText" and "historyAudio" exist,
        // you can append the new result to them (if live updates are desired).
        const newTextEntry = document.createElement('li');
        newTextEntry.innerHTML = `
          <p><strong>${new Date().toLocaleString()}</strong></p>
          <p><strong>Q:</strong> ${result.transcribed_question}</p>
          <p><strong>A:</strong> ${result.answer_text}</p>
        `;
        const newAudioEntry = document.createElement('li');
        newAudioEntry.innerHTML = `
          <audio controls>
            <source src="/uploads/${result.tts_file}" type="audio/mp3">
            Your browser does not support audio.
          </audio>
        `;
        // Append to history panels if they exist:
        const historyTextPanel = document.getElementById('historyText');
        const historyAudioPanel = document.getElementById('historyAudio');
        if(historyTextPanel && historyAudioPanel) {
          historyTextPanel.appendChild(newTextEntry);
          historyAudioPanel.appendChild(newAudioEntry);
        }
        timerEl.textContent = "Response ready!";
      } else {
        displayError("Upload failed: No TTS file information received.");
      }
    } catch (err) {
      console.error("[ERROR] Upload process failed:", err);
      displayError("Failed to process your question.");
    }
  };
  recordBtn.disabled = false;
  stopBtn.disabled = true;
});

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}
