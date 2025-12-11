// Venom OS - Audio Module
// Obsługa mikrofonu, wizualizacji audio i Push-to-Talk

export class AudioManager {
    constructor(dashboard) {
        this.dashboard = dashboard;
        this.audioContext = null;
        this.analyser = null;
        this.microphone = null;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.canvas = null;
        this.canvasContext = null;
        this.animationId = null;
    }

    async init() {
        // Initialize canvas for visualization
        this.canvas = document.getElementById('visualizerCanvas');
        if (this.canvas) {
            this.canvasContext = this.canvas.getContext('2d');
        }

        // Setup microphone button
        const micButton = document.getElementById('micButton');
        if (micButton) {
            // Push-to-talk: mousedown/mouseup
            micButton.addEventListener('mousedown', () => this.startRecording());
            micButton.addEventListener('mouseup', () => this.stopRecording());
            micButton.addEventListener('mouseleave', () => {
                if (this.isRecording) {
                    this.stopRecording();
                }
            });

            // Touch support
            micButton.addEventListener('touchstart', (e) => {
                e.preventDefault();
                this.startRecording();
            });
            micButton.addEventListener('touchend', (e) => {
                e.preventDefault();
                this.stopRecording();
            });
        }

        // Request microphone access
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.setupAudioContext(stream);
            
            if (micButton) {
                micButton.disabled = false;
            }

            this.dashboard.ui.showNotification('🎤 Mikrofon gotowy', 'success');
        } catch (error) {
            console.error('Błąd dostępu do mikrofonu:', error);
            this.dashboard.ui.showNotification('❌ Brak dostępu do mikrofonu', 'error');
        }
    }

    setupAudioContext(stream) {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 256;
        
        this.microphone = this.audioContext.createMediaStreamSource(stream);
        this.microphone.connect(this.analyser);

        // Setup MediaRecorder
        this.mediaRecorder = new MediaRecorder(stream);
        
        this.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                this.audioChunks.push(event.data);
            }
        };

        this.mediaRecorder.onstop = () => {
            this.processRecording();
        };
    }

    startRecording() {
        if (this.isRecording || !this.mediaRecorder) return;

        this.isRecording = true;
        this.audioChunks = [];
        this.mediaRecorder.start();

        // Start visualization
        this.startVisualization();

        // Update UI
        const micButton = document.getElementById('micButton');
        if (micButton) {
            micButton.classList.add('recording');
            micButton.querySelector('.mic-text').textContent = '🔴 Nagrywanie...';
        }

        const transcriptionText = document.getElementById('transcriptionText');
        if (transcriptionText) {
            transcriptionText.textContent = 'Słucham...';
        }
    }

    stopRecording() {
        if (!this.isRecording || !this.mediaRecorder) return;

        this.isRecording = false;
        this.mediaRecorder.stop();

        // Stop visualization
        this.stopVisualization();

        // Update UI
        const micButton = document.getElementById('micButton');
        if (micButton) {
            micButton.classList.remove('recording');
            micButton.querySelector('.mic-text').textContent = 'Przytrzymaj i mów';
        }

        const transcriptionText = document.getElementById('transcriptionText');
        if (transcriptionText) {
            transcriptionText.textContent = 'Przetwarzanie...';
        }
    }

    async processRecording() {
        if (this.audioChunks.length === 0) {
            console.warn('No audio data recorded');
            return;
        }

        const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
        
        // Send to backend for transcription
        try {
            const formData = new FormData();
            formData.append('audio', audioBlob, 'voice.webm');

            const response = await fetch('/api/v1/audio/transcribe', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            
            // Update transcription display
            const transcriptionText = document.getElementById('transcriptionText');
            if (transcriptionText) {
                transcriptionText.textContent = result.text || 'Nie rozpoznano tekstu';
            }

            // If transcription successful, send as task
            if (result.text && result.text.trim()) {
                this.dashboard.sendTaskFromVoice(result.text);
            }

        } catch (error) {
            console.error('Error processing audio:', error);
            this.dashboard.ui.showNotification('❌ Błąd przetwarzania audio', 'error');
            
            const transcriptionText = document.getElementById('transcriptionText');
            if (transcriptionText) {
                transcriptionText.textContent = 'Błąd przetwarzania';
            }
        }
    }

    startVisualization() {
        if (!this.canvas || !this.analyser) return;

        const bufferLength = this.analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        const draw = () => {
            if (!this.isRecording) return;

            this.animationId = requestAnimationFrame(draw);

            this.analyser.getByteFrequencyData(dataArray);

            // Clear canvas
            this.canvasContext.fillStyle = 'rgba(0, 0, 0, 0.8)';
            this.canvasContext.fillRect(0, 0, this.canvas.width, this.canvas.height);

            // Draw bars
            const barWidth = (this.canvas.width / bufferLength) * 2.5;
            let barHeight;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                barHeight = (dataArray[i] / 255) * this.canvas.height;

                // Gradient from green to cyan
                const gradient = this.canvasContext.createLinearGradient(0, 0, 0, this.canvas.height);
                gradient.addColorStop(0, '#00ff9d');
                gradient.addColorStop(1, '#00b8ff');

                this.canvasContext.fillStyle = gradient;
                this.canvasContext.fillRect(x, this.canvas.height - barHeight, barWidth, barHeight);

                x += barWidth + 1;
            }
        };

        draw();
    }

    stopVisualization() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
            this.animationId = null;
        }

        // Clear canvas
        if (this.canvas && this.canvasContext) {
            this.canvasContext.fillStyle = 'rgba(0, 0, 0, 0.8)';
            this.canvasContext.fillRect(0, 0, this.canvas.width, this.canvas.height);
        }
    }

    destroy() {
        this.stopVisualization();
        
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
        
        if (this.microphone) {
            this.microphone.disconnect();
        }
        
        if (this.audioContext) {
            this.audioContext.close();
        }
    }
}
