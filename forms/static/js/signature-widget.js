/**
 * Signature Widget for Forms Service
 * Uses signature_pad.js for drawing signatures
 */

class SignatureWidget {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Container element '${containerId}' not found`);
        }

        this.options = {
            width: options.width || 400,
            height: options.height || 200,
            penColor: options.penColor || '#000000',
            backgroundColor: options.backgroundColor || '#ffffff',
            onSign: options.onSign || null,
            onClear: options.onClear || null,
            ...options
        };

        this.signaturePad = null;
        this.init();
    }

    init() {
        // Create canvas element
        this.canvas = document.createElement('canvas');
        this.canvas.width = this.options.width;
        this.canvas.height = this.options.height;
        this.canvas.className = 'signature-pad';
        this.canvas.style.border = '1px solid #dee2e6';
        this.canvas.style.borderRadius = '4px';
        this.canvas.style.touchAction = 'none';

        // Create wrapper
        const wrapper = document.createElement('div');
        wrapper.className = 'signature-pad-container';
        wrapper.appendChild(this.canvas);

        // Create controls
        const controls = document.createElement('div');
        controls.className = 'signature-controls mt-2';
        controls.innerHTML = `
            <button type="button" class="btn btn-sm btn-outline-secondary me-2" id="${this.container.id}-clear">
                <i class="bi bi-eraser"></i> Clear
            </button>
            <button type="button" class="btn btn-sm btn-outline-secondary me-2" id="${this.container.id}-undo">
                <i class="bi bi-arrow-counterclockwise"></i> Undo
            </button>
            <span class="text-muted small ms-2" id="${this.container.id}-status">Draw your signature above</span>
        `;
        wrapper.appendChild(controls);

        // Add to container
        this.container.innerHTML = '';
        this.container.appendChild(wrapper);

        // Initialize signature_pad
        this.signaturePad = new SignaturePad(this.canvas, {
            penColor: this.options.penColor,
            backgroundColor: this.options.backgroundColor,
            minWidth: 0.5,
            maxWidth: 2.5,
            throttle: 16
        });

        // Event listeners
        document.getElementById(`${this.container.id}-clear`).addEventListener('click', () => this.clear());
        document.getElementById(`${this.container.id}-undo`).addEventListener('click', () => this.undo());

        // Track when signature is drawn
        this.signaturePad.addEventListener('endStroke', () => {
            this.updateStatus();
            if (this.options.onSign) {
                this.options.onSign(this.getData());
            }
        });

        // Handle window resize
        window.addEventListener('resize', () => this.resizeCanvas());
    }

    clear() {
        this.signaturePad.clear();
        this.updateStatus();
        if (this.options.onClear) {
            this.options.onClear();
        }
    }

    undo() {
        const data = this.signaturePad.toData();
        if (data && data.length > 0) {
            data.pop();
            this.signaturePad.fromData(data);
            this.updateStatus();
        }
    }

    isEmpty() {
        return this.signaturePad.isEmpty();
    }

    getData(format = 'base64') {
        if (this.isEmpty()) {
            return null;
        }

        if (format === 'base64') {
            return this.signaturePad.toDataURL('image/png');
        } else if (format === 'svg') {
            return this.signaturePad.toDataURL('image/svg+xml');
        } else if (format === 'points') {
            return this.signaturePad.toData();
        }

        return this.signaturePad.toDataURL();
    }

    setData(data) {
        if (typeof data === 'string' && data.startsWith('data:')) {
            // Base64 image
            this.signaturePad.fromDataURL(data);
        } else if (Array.isArray(data)) {
            // Points array
            this.signaturePad.fromData(data);
        }
        this.updateStatus();
    }

    updateStatus() {
        const statusEl = document.getElementById(`${this.container.id}-status`);
        if (statusEl) {
            if (this.isEmpty()) {
                statusEl.textContent = 'Draw your signature above';
                statusEl.className = 'text-muted small ms-2';
            } else {
                statusEl.textContent = 'Signature captured';
                statusEl.className = 'text-success small ms-2';
            }
        }
    }

    resizeCanvas() {
        // Save current signature
        const data = this.signaturePad.toData();

        // Resize canvas
        const ratio = Math.max(window.devicePixelRatio || 1, 1);
        this.canvas.width = this.canvas.offsetWidth * ratio;
        this.canvas.height = this.canvas.offsetHeight * ratio;
        this.canvas.getContext('2d').scale(ratio, ratio);

        // Restore signature
        this.signaturePad.clear();
        if (data) {
            this.signaturePad.fromData(data);
        }
    }

    enable() {
        this.signaturePad.on();
    }

    disable() {
        this.signaturePad.off();
    }
}

/**
 * Typed Signature Widget
 * For users who prefer to type their signature
 */
class TypedSignatureWidget {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Container element '${containerId}' not found`);
        }

        this.options = {
            fontFamily: options.fontFamily || "'Brush Script MT', cursive",
            fontSize: options.fontSize || '32px',
            onChange: options.onChange || null,
            ...options
        };

        this.init();
    }

    init() {
        this.container.innerHTML = `
            <div class="typed-signature-container">
                <input type="text"
                       class="form-control form-control-lg"
                       id="${this.container.id}-input"
                       placeholder="Type your full name"
                       style="font-family: ${this.options.fontFamily}; font-size: ${this.options.fontSize};">
                <div class="signature-preview mt-2 p-3 border rounded bg-white text-center"
                     id="${this.container.id}-preview"
                     style="font-family: ${this.options.fontFamily}; font-size: ${this.options.fontSize}; min-height: 60px;">
                </div>
            </div>
        `;

        this.input = document.getElementById(`${this.container.id}-input`);
        this.preview = document.getElementById(`${this.container.id}-preview`);

        this.input.addEventListener('input', () => {
            this.preview.textContent = this.input.value;
            if (this.options.onChange) {
                this.options.onChange(this.getData());
            }
        });
    }

    isEmpty() {
        return !this.input.value.trim();
    }

    getData() {
        return this.input.value.trim();
    }

    setData(value) {
        this.input.value = value;
        this.preview.textContent = value;
    }

    clear() {
        this.input.value = '';
        this.preview.textContent = '';
    }
}

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { SignatureWidget, TypedSignatureWidget };
}
