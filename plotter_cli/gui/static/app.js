// Plotter Studio - Modern Application JavaScript

// Helper function to create Lucide icons
function createLucideIcon(name, size = 16, className = '') {
  const icon = document.createElement('i');
  icon.setAttribute('data-lucide', name);
  icon.style.width = `${size}px`;
  icon.style.height = `${size}px`;
  if (className) icon.className = className;
  return icon;
}

// Helper function to create Lucide icon HTML string
function lucideIconHTML(name, size = 16, className = '', style = '') {
  const classAttr = className ? ` class="${className}"` : '';
  const styleAttr = style ? ` style="${style}"` : ` style="width: ${size}px; height: ${size}px;"`;
  return `<i data-lucide="${name}"${classAttr}${styleAttr}></i>`;
}

// Modal helper functions
function showAlert(title, message, type = 'info') {
  return new Promise((resolve) => {
    const modal = document.getElementById('alert-modal');
    const titleEl = document.getElementById('alert-title');
    const messageEl = document.getElementById('alert-message');
    const okBtn = document.getElementById('alert-ok-btn');
    const closeBtn = document.getElementById('close-alert-btn');

    if (!modal || !titleEl || !messageEl || !okBtn) return resolve();

    // Set icon based on type
    let iconName = 'info';
    if (type === 'success') iconName = 'check-circle-2';
    else if (type === 'error') iconName = 'alert-circle';
    else if (type === 'warning') iconName = 'alert-triangle';

    // Update title with icon
    titleEl.innerHTML = `<i data-lucide="${iconName}" style="width: 18px; height: 18px;"></i> ${title}`;
    messageEl.textContent = message;

    const closeModal = () => {
      modal.classList.remove('active');
      resolve();
    };

    okBtn.onclick = closeModal;
    closeBtn.onclick = closeModal;
    modal.onclick = (e) => {
      if (e.target === modal) closeModal();
    };

    modal.classList.add('active');
    if (window.lucide) lucide.createIcons({ nodes: [modal] });
  });
}

function showConfirm(title, message) {
  return new Promise((resolve) => {
    const modal = document.getElementById('confirm-modal');
    const titleEl = document.getElementById('confirm-title');
    const messageEl = document.getElementById('confirm-message');
    const okBtn = document.getElementById('confirm-ok-btn');
    const cancelBtn = document.getElementById('confirm-cancel-btn');
    const closeBtn = document.getElementById('close-confirm-btn');

    if (!modal || !titleEl || !messageEl || !okBtn || !cancelBtn) return resolve(false);

    titleEl.textContent = title;
    messageEl.textContent = message;

    const closeModal = (result) => {
      modal.classList.remove('active');
      resolve(result);
    };

    okBtn.onclick = () => closeModal(true);
    cancelBtn.onclick = () => closeModal(false);
    closeBtn.onclick = () => closeModal(false);
    modal.onclick = (e) => {
      if (e.target === modal) closeModal(false);
    };

    modal.classList.add('active');
  });
}

// Item 17: Toast notification system
function showToast(message, type = 'success', duration = 3000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  const colors = { success: '#2a9d5c', error: '#c0392b', info: '#2980b9' };
  const bgColor = colors[type] || colors.success;

  toast.style.cssText = `
    background: ${bgColor};
    color: #fff;
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-family: Inter, sans-serif;
    max-width: 320px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    transform: translateX(120%);
    transition: transform 0.25s ease;
    pointer-events: auto;
    cursor: pointer;
    line-height: 1.4;
    word-break: break-all;
  `;
  toast.textContent = message;
  container.appendChild(toast);

  // Slide in
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      toast.style.transform = 'translateX(0)';
    });
  });

  const dismiss = () => {
    toast.style.transform = 'translateX(120%)';
    setTimeout(() => toast.remove(), 280);
  };

  toast.addEventListener('click', dismiss);
  setTimeout(dismiss, duration);
}

class PlotterStudio {
  constructor() {
    this.canvas = document.getElementById('canvas');
    this.ctx = this.canvas.getContext('2d');
    this.container = document.getElementById('canvas-container');

    this.papers = [];
    this.svgLibrary = [];
    this.selectedPaperId = null;
    this.selectedPaperIds = new Set(); // multi-select
    this.settings = null;

    this.scale = 2; // pixels per mm
    this.canvasWidth = 880;
    this.canvasHeight = 470;

    // Canvas transform (pan & zoom)
    this.canvasTransform = { x: 0, y: 0, scale: 1 };
    this.activeTool = 'select';

    // Dragging state
    this.dragging = false;
    this.panning = false;
    this.dragStart = { x: 0, y: 0 };
    this.dragStartTransform = null;
    this.dragStartPositions = {}; // for multi-select drag

    // Snap-to-grid
    this.snapToGrid = false;

    // Last mouse event (for zoom coordinate update)
    this.lastMouseEvent = null;

    // Undo/redo stacks
    this.undoStack = [];
    this.redoStack = [];

    this.init();
  }

  // ─── Utility ───────────────────────────────────────────────────────────────

  _debounce(fn, delay = 300) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  }

  refresh({ paperList = true, inspector = true, render = true } = {}) {
    if (paperList) this.updatePaperList();
    this.updateAutoAssignVisibility();
    if (inspector) this.updateInspector();
    if (render) this.render();
  }

  // ─── Undo / Redo ──────────────────────────────────────────────────────────

  _saveUndoSnapshot() {
    const snapshot = this.papers.map(p => ({ ...p }));
    this.undoStack.push(snapshot);
    if (this.undoStack.length > 50) this.undoStack.shift();
    this.redoStack = [];
    this._updateUndoRedoButtons();
  }

  _updateUndoRedoButtons() {
    const undoBtn = document.getElementById('undo-btn');
    const redoBtn = document.getElementById('redo-btn');
    if (undoBtn) undoBtn.disabled = this.undoStack.length === 0;
    if (redoBtn) redoBtn.disabled = this.redoStack.length === 0;
  }

  async _restoreSnapshot(snapshot) {
    try {
      await fetch('/api/bulk-update-papers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ papers: snapshot }),
      });
      this.papers = snapshot.map(p => ({ ...p }));
      this.refresh();
    } catch (e) {
      console.error('Failed to restore snapshot:', e);
    }
  }

  async undo() {
    if (this.undoStack.length === 0) return;
    const snapshot = this.undoStack.pop();
    this.redoStack.push(this.papers.map(p => ({ ...p })));
    this._updateUndoRedoButtons();
    await this._restoreSnapshot(snapshot);
  }

  async redo() {
    if (this.redoStack.length === 0) return;
    const snapshot = this.redoStack.pop();
    this.undoStack.push(this.papers.map(p => ({ ...p })));
    this._updateUndoRedoButtons();
    await this._restoreSnapshot(snapshot);
  }

  async init() {
    await this.loadSettings();
    this.setupCanvas();
    this.setupEventListeners();
    this.setupCalibration();
    await Promise.all([this.loadSvgLibrary(), this.loadPapers()]);
    this.render();
    this.updateInspector();
  }

  setupCustomTitleBar() {
    // Check if we're in a pywebview frameless window
    const titleBar = document.getElementById('custom-title-bar');
    if (!titleBar) {
      console.log('Custom title bar element not found');
      return;
    }

    // Function to wire up traffic lights with API
    const wireTrafficLights = () => {
      const closeBtn = document.getElementById('traffic-light-close');
      const minimizeBtn = document.getElementById('traffic-light-minimize');
      const maximizeBtn = document.getElementById('traffic-light-maximize');

      // Check if pywebview API is available
      if (window.pywebview && window.pywebview.api) {
        console.log('Wiring up traffic lights with pywebview API');
        console.log('Available API methods:', Object.keys(window.pywebview.api));

        if (closeBtn && window.pywebview.api.close) {
          closeBtn.onclick = (e) => {
            e.stopPropagation();
            e.preventDefault();
            try {
              window.pywebview.api.close();
            } catch (err) {
              console.error('Error closing window:', err);
            }
          };
        }

        if (minimizeBtn && window.pywebview.api.minimize) {
          minimizeBtn.onclick = (e) => {
            e.stopPropagation();
            e.preventDefault();
            try {
              window.pywebview.api.minimize();
            } catch (err) {
              console.error('Error minimizing window:', err);
            }
          };
        }

        if (maximizeBtn && window.pywebview.api.maximize) {
          maximizeBtn.onclick = (e) => {
            e.stopPropagation();
            e.preventDefault();
            try {
              window.pywebview.api.maximize();
            } catch (err) {
              console.error('Error maximizing window:', err);
            }
          };
        }
      } else {
        console.log('Pywebview API not yet available');
      }
    };

    // Check if we're in frameless mode
    // Check multiple indicators: URL param, window flag, or pywebview API
    const urlParams = new URLSearchParams(window.location.search);
    const framelessParam = urlParams.get('frameless') === 'true';
    const framelessFlag = window.FRAMELESS_MODE === true || window.FRAMELESS_MODE === 'true';
    const hasPywebview = window.pywebview && window.pywebview.api;
    
    const isFrameless = framelessParam || framelessFlag || hasPywebview;
    
    console.log('Frameless detection:', {
      framelessParam,
      framelessFlag,
      hasPywebview,
      isFrameless,
      windowPywebview: !!window.pywebview
    });
    
    if (isFrameless) {
      console.log('Detected native window, showing custom title bar');
      titleBar.style.display = 'flex';
      titleBar.classList.add('frameless');
      
      // Wire up traffic lights immediately
      wireTrafficLights();
      
      // Also listen for pywebviewready event
      window.addEventListener('pywebviewready', () => {
        console.log('Pywebview ready event fired');
        wireTrafficLights();
      });
      
      // Retry wiring after delays (API might load asynchronously)
      setTimeout(wireTrafficLights, 100);
      setTimeout(wireTrafficLights, 500);
      setTimeout(wireTrafficLights, 1000);
    } else {
      console.log('Not in native window, hiding custom title bar');
      titleBar.style.display = 'none';
    }
  }

  async loadSettings() {
    try {
      const response = await fetch('/api/settings');
      this.settings = await response.json();
      this.canvasWidth = this.settings.area_width;
      this.canvasHeight = this.settings.area_height;
      this.setupCanvas();
      this.populatePaperSelects();
      this.updateBedInfo();
      this.updateCalibrationStatusUI(this.settings);
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  }

  openSettings() {
    const modal = document.getElementById('settings-modal');
    if (!modal) return;

    // Populate form with current settings
    if (this.settings) {
      document.getElementById('settings-area-width').value = this.settings.area_width;
      document.getElementById('settings-area-height').value = this.settings.area_height;
      document.getElementById('settings-paper-gap').value = this.settings.paper_gap ?? 30;
      document.getElementById('settings-z-up-long').value = this.settings.z_up_long;
      document.getElementById('settings-z-up-short').value = this.settings.z_up_short;
      document.getElementById('settings-z-up-threshold').value = this.settings.z_up_threshold;
      document.getElementById('settings-z-down').value = this.settings.z_down;
      document.getElementById('settings-feed-rate-draw').value = this.settings.feed_rate_draw;
      document.getElementById('settings-feed-rate-travel').value = this.settings.feed_rate_travel;
      document.getElementById('settings-feed-rate-z').value = this.settings.feed_rate_z;
      document.getElementById('settings-registration-marks-length').value = this.settings.registration_marks_length;
      const hmp = document.getElementById('settings-height-map-path');
      if (hmp) hmp.value = this.settings.height_map_path || '';
      document.getElementById('settings-path-sorting').checked = this.settings.path_sorting !== false;
      document.getElementById('settings-path-reversing').checked = this.settings.path_reversing !== false;
      this.updateCalibrationStatusUI(this.settings);
    }

    modal.classList.add('active');
    if (window.lucide) lucide.createIcons({ nodes: [modal] });
  }

  async saveSettings() {
    try {
      const settingsData = {
        area_width: parseFloat(document.getElementById('settings-area-width').value),
        area_height: parseFloat(document.getElementById('settings-area-height').value),
        paper_gap: parseFloat(document.getElementById('settings-paper-gap').value),
        z_up_long: parseFloat(document.getElementById('settings-z-up-long').value),
        z_up_short: parseFloat(document.getElementById('settings-z-up-short').value),
        z_up_threshold: parseFloat(document.getElementById('settings-z-up-threshold').value),
        z_down: parseFloat(document.getElementById('settings-z-down').value),
        feed_rate_draw: parseInt(document.getElementById('settings-feed-rate-draw').value),
        feed_rate_travel: parseInt(document.getElementById('settings-feed-rate-travel').value),
        feed_rate_z: parseInt(document.getElementById('settings-feed-rate-z').value),
        registration_marks_length: parseFloat(document.getElementById('settings-registration-marks-length').value),
        path_sorting: document.getElementById('settings-path-sorting').checked,
        path_reversing: document.getElementById('settings-path-reversing').checked,
        height_map_path: (document.getElementById('settings-height-map-path')?.value ?? '').trim(),
      };

      // Validate inputs
      if (isNaN(settingsData.area_width) || settingsData.area_width <= 0) {
        await showAlert('Error', 'Canvas width must be a positive number', 'error');
        return;
      }
      if (isNaN(settingsData.area_height) || settingsData.area_height <= 0) {
        await showAlert('Error', 'Canvas height must be a positive number', 'error');
        return;
      }
      if (isNaN(settingsData.paper_gap) || settingsData.paper_gap < 0) {
        await showAlert('Error', 'Paper gap must be zero or a positive number', 'error');
        return;
      }

      const response = await fetch('/api/settings', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(settingsData),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to save settings');
      }

      const result = await response.json();

      // Update local settings
      this.settings = { ...this.settings, ...settingsData };

      // Check if canvas dimensions changed
      const canvasChanged = 
        this.canvasWidth !== settingsData.area_width ||
        this.canvasHeight !== settingsData.area_height;

      if (canvasChanged) {
        this.canvasWidth = settingsData.area_width;
        this.canvasHeight = settingsData.area_height;
        this.setupCanvas();
        this.updateBedInfo();
        this.render();
      }

      // Close modal
      document.getElementById('settings-modal').classList.remove('active');
      await this.updateHeightMapIndicator();

      await showAlert('Settings Saved', 'Settings have been saved successfully.', 'success');
    } catch (error) {
      console.error('Error saving settings:', error);
      await showAlert('Error', 'Failed to save settings: ' + error.message, 'error');
    }
  }

  updateBedInfo() {
    const widthEl = document.getElementById('bed-width');
    const heightEl = document.getElementById('bed-height');
    const sizeEl = document.getElementById('canvas-size');
    if (widthEl) widthEl.textContent = `${this.canvasWidth}mm`;
    if (heightEl) heightEl.textContent = `${this.canvasHeight}mm`;
    if (sizeEl) sizeEl.textContent = `${this.canvasWidth} × ${this.canvasHeight}mm`;
  }

  formatShortPath(path) {
    if (!path) return '';
    const parts = path.split('/');
    if (parts.length <= 3) return path;
    return `.../${parts.slice(-2).join('/')}`;
  }

  updateCalibrationStatusUI(status = this.settings) {
    const headerPill = document.getElementById('calibration-header-pill');
    const card = document.getElementById('height-map-status');
    const label = document.getElementById('height-map-indicator');
    const detail = document.getElementById('height-map-status-detail');
    const settingsBanner = document.getElementById('settings-height-map-status');

    const willApply = Boolean(status?.height_map_will_apply);
    const effectivePath = status?.height_map_effective_path || '';
    const configuredPath = status?.height_map_configured_path || status?.height_map_path || '';
    const hasConfiguredPath = configuredPath.trim() !== '';
    const missingConfiguredMap = hasConfiguredPath && !willApply;
    const source = status?.height_map_source === 'default' ? 'saved calibration map' : 'configured map';

    const setClass = (el, base, stateClass) => {
      if (!el) return;
      el.className = stateClass ? `${base} ${stateClass}` : base;
    };

    if (willApply) {
      setClass(headerPill, 'calibration-header-pill', '');
      setClass(card, 'calibration-status-card', '');
      setClass(settingsBanner, 'calibration-settings-banner', '');
      if (headerPill) {
        headerPill.textContent = 'Calibration: SET - WILL BE USED';
        headerPill.title = effectivePath;
      }
      if (label) label.textContent = 'SET - WILL BE USED';
      if (detail) {
        detail.textContent = `Exports will apply the ${source}: ${this.formatShortPath(effectivePath)}`;
        detail.title = effectivePath;
      }
      if (settingsBanner) {
        settingsBanner.textContent = `Calibration map is set and WILL BE USED on export. Path: ${effectivePath}`;
        settingsBanner.title = effectivePath;
      }
      return;
    }

    if (missingConfiguredMap) {
      setClass(headerPill, 'calibration-header-pill', 'calibration-header-pill-warning');
      setClass(card, 'calibration-status-card', 'calibration-status-card-warning');
      setClass(settingsBanner, 'calibration-settings-banner', 'calibration-settings-banner-warning');
      if (headerPill) {
        headerPill.textContent = 'Calibration: path missing';
        headerPill.title = configuredPath;
      }
      if (label) label.textContent = 'PATH MISSING';
      if (detail) {
        detail.textContent = `Configured map was not found: ${this.formatShortPath(configuredPath)}`;
        detail.title = configuredPath;
      }
      if (settingsBanner) {
        settingsBanner.textContent = `Calibration path is set, but the file was not found. Exports will fail until this is fixed: ${configuredPath}`;
        settingsBanner.title = configuredPath;
      }
      return;
    }

    setClass(headerPill, 'calibration-header-pill', 'calibration-header-pill-muted');
    setClass(card, 'calibration-status-card', 'calibration-status-card-muted');
    setClass(settingsBanner, 'calibration-settings-banner', 'calibration-settings-banner-muted');
    if (headerPill) {
      headerPill.textContent = 'Calibration: not set';
      headerPill.title = '';
    }
    if (label) label.textContent = 'Not set';
    if (detail) {
      detail.textContent = 'Exports will not use surface correction.';
      detail.title = '';
    }
    if (settingsBanner) {
      settingsBanner.textContent = 'Calibration map not set. Exports will use uncorrected Z.';
      settingsBanner.title = '';
    }
  }

  setupCanvas() {
    const pixelWidth = this.canvasWidth * this.scale;
    const pixelHeight = this.canvasHeight * this.scale;

    this.canvas.width = pixelWidth;
    this.canvas.height = pixelHeight;
    this.canvas.style.width = `${pixelWidth}px`;
    this.canvas.style.height = `${pixelHeight}px`;
    
    // Center canvas initially
    this.centerCanvas();
  }

  setupEventListeners() {
    // Setup custom title bar (for frameless windows)
    this.setupCustomTitleBar();
    
    // File input
    const fileInput = document.getElementById('file-input');
    const addSvgBtn = document.getElementById('add-svg-btn');
    addSvgBtn?.addEventListener('click', () => fileInput?.click());
    fileInput?.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        this.addSvg(e.target.files[0]);
      }
    });

    // Drag and drop SVG files onto the window
    document.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
    });
    document.addEventListener('drop', (e) => {
      e.preventDefault();
      const files = Array.from(e.dataTransfer.files).filter(
        (f) => f.name.toLowerCase().endsWith('.svg')
      );
      for (const file of files) {
        this.addSvg(file);
      }
    });

    // Clear All
    document.getElementById('settings-btn')?.addEventListener('click', () => this.openSettings());
    document.getElementById('clear-all-btn')?.addEventListener('click', () => this.clearAll());

    // Export
    document.getElementById('export-btn')?.addEventListener('click', () => this.export());

    // Add paper modal
    const addPaperBtn = document.getElementById('add-paper-btn');
    const paperModal = document.getElementById('paper-modal');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const confirmAddBtn = document.getElementById('confirm-add-paper-btn');

    addPaperBtn?.addEventListener('click', () => {
      // Item 28: reset unit selector on open
      const unitSelect = document.getElementById('custom-paper-unit');
      if (unitSelect) {
        unitSelect.value = 'mm';
        unitSelect.dispatchEvent(new Event('change'));
      }
      const paperSelect = document.getElementById('add-paper-select');
      if (paperSelect) {
        paperSelect.value = '';
        this.toggleCustomPaperInputs(false);
      }
      paperModal?.classList.add('active');
    });

    closeModalBtn?.addEventListener('click', () => {
      this.closePaperModal();
    });

    // Item 25: backdrop click closes paper modal
    paperModal?.addEventListener('click', (e) => {
      if (e.target === paperModal) this.closePaperModal();
    });

    confirmAddBtn?.addEventListener('click', () => {
      this.addPaperFromSelect();
    });

    // Settings modal
    const settingsModal = document.getElementById('settings-modal');
    const closeSettingsBtn = document.getElementById('close-settings-btn');
    const settingsCancelBtn = document.getElementById('settings-cancel-btn');
    const settingsSaveBtn = document.getElementById('settings-save-btn');

    closeSettingsBtn?.addEventListener('click', () => {
      settingsModal?.classList.remove('active');
    });

    settingsCancelBtn?.addEventListener('click', () => {
      settingsModal?.classList.remove('active');
    });

    settingsSaveBtn?.addEventListener('click', () => {
      this.saveSettings();
    });

    // Close settings modal when clicking outside
    settingsModal?.addEventListener('click', (e) => {
      if (e.target === settingsModal) {
        settingsModal.classList.remove('active');
      }
    });

    // Auto-arrange
    document.getElementById('auto-arrange-btn')?.addEventListener('click', () => this.autoArrange());
    document.getElementById('auto-assign-btn')?.addEventListener('click', () => this.autoAssignSvgs());

    // Alignment buttons (Item 20)
    document.querySelectorAll('[data-align]').forEach(btn => {
      btn.addEventListener('click', () => this.alignPapers(btn.dataset.align));
    });

    // Toolbar tools
    document.getElementById('tool-select')?.addEventListener('click', () => this.setTool('select'));
    document.getElementById('tool-pan')?.addEventListener('click', () => this.setTool('pan'));

    // Snap-to-grid toggle (Item 21)
    document.getElementById('snap-grid-btn')?.addEventListener('click', () => this.toggleSnapToGrid());

    // Undo/redo buttons (Item 23)
    document.getElementById('undo-btn')?.addEventListener('click', () => this.undo());
    document.getElementById('redo-btn')?.addEventListener('click', () => this.redo());

    // Help button (Item 26)
    document.getElementById('help-btn')?.addEventListener('click', () => this.showHelp());

    // Zoom controls
    document.getElementById('zoom-in-btn')?.addEventListener('click', () => this.zoomIn());
    document.getElementById('zoom-out-btn')?.addEventListener('click', () => this.zoomOut());
    document.getElementById('zoom-level')?.addEventListener('click', () => this.resetView());

    // Fullscreen toggle
    document.getElementById('fullscreen-btn')?.addEventListener('click', () => this.toggleFullscreen());

    // Listen for fullscreen changes (e.g., ESC key)
    document.addEventListener('fullscreenchange', () => {
      this.updateFullscreenIcon();
    });

    // Canvas mouse events
    this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
    // Item 6: single merged mousemove listener
    this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
    this.canvas.addEventListener('mouseup', () => this.onMouseUp());
    this.canvas.addEventListener('wheel', (e) => this.onWheel(e), { passive: false });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      const isTyping = e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA';
      if (isTyping) return;

      if (e.key === 'v' || e.key === 'V') this.setTool('select');
      if (e.key === 'h' || e.key === 'H') this.setTool('pan');
      if (e.key === '?') { e.preventDefault(); this.showHelp(); }
      if (e.key === 'Escape' || e.key === 'Esc') {
        if (this.activeTool === 'pan') {
          e.preventDefault();
          this.setTool('select');
        }
      }
      if (e.key === ' ') {
        e.preventDefault();
        this.panning = true;
        this.canvas.style.cursor = 'grabbing';
      }

      // Item 18: Delete/Backspace removes selected paper(s)
      if ((e.key === 'Delete' || e.key === 'Backspace') && (this.selectedPaperId || this.selectedPaperIds.size > 0)) {
        e.preventDefault();
        this.removeSelectedPaper();
      }

      // Item 19: Arrow keys nudge selected paper
      const arrowKeys = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'];
      if (arrowKeys.includes(e.key) && this.selectedPaperId) {
        e.preventDefault();
        const step = e.shiftKey ? 0.1 : 1;
        const paper = this.papers.find(p => p.id === this.selectedPaperId);
        if (paper && !paper.locked) {
          if (e.key === 'ArrowLeft') paper.x = (paper.x || 0) - step;
          if (e.key === 'ArrowRight') paper.x = (paper.x || 0) + step;
          if (e.key === 'ArrowUp') paper.y = (paper.y || 0) - step;
          if (e.key === 'ArrowDown') paper.y = (paper.y || 0) + step;
          this.render();
          // Update inspector inputs
          const xInput = document.getElementById('inspector-x');
          const yInput = document.getElementById('inspector-y');
          if (xInput) xInput.value = paper.x.toFixed(1);
          if (yInput) yInput.value = paper.y.toFixed(1);
          // Debounced backend update
          if (!this._nudgeDebounced) {
            this._nudgeDebounced = this._debounce((pid) => {
              const p = this.papers.find(pp => pp.id === pid);
              if (p) this.updatePaperPosition('x', p.x).then(() => this.updatePaperPosition('y', p.y));
            }, 300);
          }
          this._nudgeDebounced(paper.id);
        }
      }

      // Undo/redo (Item 23)
      if ((e.metaKey || e.ctrlKey) && e.key === 'z') {
        e.preventDefault();
        if (e.shiftKey) this.redo();
        else this.undo();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'y') {
        e.preventDefault();
        this.redo();
      }

      // Cmd/Ctrl+D: clone selected paper
      if ((e.metaKey || e.ctrlKey) && (e.key === 'd' || e.key === 'D')) {
        e.preventDefault();
        if (this.selectedPaperId) this.cloneSelectedPaper();
      }
    });

    document.addEventListener('keyup', (e) => {
      if (e.key === ' ') {
        this.panning = false;
        this.canvas.style.cursor = this.activeTool === 'pan' ? 'grab' : 'crosshair';
      }
    });

    // Close help modal
    document.getElementById('close-help-btn')?.addEventListener('click', () => {
      document.getElementById('help-modal')?.classList.remove('active');
    });
    document.getElementById('help-modal')?.addEventListener('click', (e) => {
      if (e.target === document.getElementById('help-modal')) {
        document.getElementById('help-modal').classList.remove('active');
      }
    });
  }

  showHelp() {
    document.getElementById('help-modal')?.classList.add('active');
    if (window.lucide) lucide.createIcons({ nodes: [document.getElementById('help-modal')] });
  }

  toggleSnapToGrid() {
    this.snapToGrid = !this.snapToGrid;
    const btn = document.getElementById('snap-grid-btn');
    if (btn) btn.classList.toggle('active', this.snapToGrid);
    this.render();
  }

  setTool(tool) {
    this.activeTool = tool;
    document.querySelectorAll('.tool-btn').forEach(btn => btn.classList.remove('active'));
    const toolBtn = document.getElementById(`tool-${tool}`);
    if (toolBtn) toolBtn.classList.add('active');
    this.canvas.style.cursor = tool === 'pan' ? 'grab' : 'crosshair';
    
    // Stop panning if switching away from pan tool
    if (tool !== 'pan' && this.panning) {
      this.panning = false;
    }
  }

  zoomIn() {
    this.canvasTransform.scale = Math.min(this.canvasTransform.scale * 1.2, 5);
    this.updateZoomDisplay();
    this.render();
  }

  zoomOut() {
    this.canvasTransform.scale = Math.max(this.canvasTransform.scale / 1.2, 0.1);
    this.updateZoomDisplay();
    this.render();
  }

  resetView() {
    this.canvasTransform = { x: 0, y: 0, scale: 1 };
    this.updateZoomDisplay();
    this.render();
    // Center the canvas in the container
    this.centerCanvas();
  }

  toggleFullscreen() {
    const appContainer = document.querySelector('.app-container');
    if (!appContainer) return;

    if (!document.fullscreenElement) {
      // Enter fullscreen
      appContainer.requestFullscreen().catch((err) => {
        console.error('Error entering fullscreen:', err);
      });
    } else {
      // Exit fullscreen
      document.exitFullscreen().catch((err) => {
        console.error('Error exiting fullscreen:', err);
      });
    }
  }

  updateFullscreenIcon() {
    const fullscreenBtn = document.getElementById('fullscreen-btn');
    const icon = fullscreenBtn?.querySelector('[data-lucide]');
    if (!icon) return;

    if (document.fullscreenElement) {
      icon.setAttribute('data-lucide', 'minimize');
    } else {
      icon.setAttribute('data-lucide', 'maximize');
    }
    if (window.lucide) lucide.createIcons({ nodes: [fullscreenBtn] });
  }

  centerCanvas() {
    // Transform starts at 0,0 (centered)
    // Canvas centering is handled by CSS flexbox in the container
    this.canvasTransform.x = 0;
    this.canvasTransform.y = 0;
    this.render();
  }

  updateZoomDisplay() {
    const zoomEl = document.getElementById('zoom-level');
    if (zoomEl) zoomEl.textContent = `${Math.round(this.canvasTransform.scale * 100)}%`;
  }

  onWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    this.canvasTransform.scale = Math.min(Math.max(this.canvasTransform.scale * delta, 0.1), 5);
    this.updateZoomDisplay();
    this.render();
    // Item 27: update coordinate label using last known mouse position
    if (this.lastMouseEvent) {
      const point = this.getCanvasPoint(this.lastMouseEvent);
      const mouseLabel = document.getElementById('mouse-position');
      if (mouseLabel) {
        mouseLabel.textContent = `${point.x.toFixed(1)}mm, ${point.y.toFixed(1)}mm`;
      }
    }
  }

  populatePaperSelects() {
    if (!this.settings || !this.settings.papers) return;

    const select = document.getElementById('add-paper-select');
    if (!select) return;

    select.innerHTML = '<option value="">Select paper size...</option>';

    for (const paper of this.settings.papers) {
      const landscape = document.createElement('option');
      landscape.value = `${paper.name}_landscape`;
      landscape.textContent = `${paper.name} (Landscape) - ${paper.width.toFixed(0)}×${paper.height.toFixed(0)}mm`;
      select.appendChild(landscape);

      const portrait = document.createElement('option');
      portrait.value = `${paper.name}_portrait`;
      portrait.textContent = `${paper.name} (Portrait) - ${paper.height.toFixed(0)}×${paper.width.toFixed(0)}mm`;
      select.appendChild(portrait);
    }

    // Add custom option
    const customOption = document.createElement('option');
    customOption.value = 'custom';
    customOption.textContent = 'Custom Size...';
    select.appendChild(customOption);

    // Add event listener to show/hide custom inputs
    select.addEventListener('change', () => {
      this.toggleCustomPaperInputs(select.value === 'custom');
    });

    // Add event listener for unit change to update input step
    const unitSelect = document.getElementById('custom-paper-unit');
    if (unitSelect) {
      unitSelect.addEventListener('change', () => {
        this.updateCustomInputStep();
      });
    }
  }

  toggleCustomPaperInputs(show) {
    const customInputs = document.getElementById('custom-paper-inputs');
    if (customInputs) {
      customInputs.style.display = show ? 'block' : 'none';
      if (show) {
        this.updateCustomInputStep();
      }
    }
  }

  updateCustomInputStep() {
    const unitSelect = document.getElementById('custom-paper-unit');
    const widthInput = document.getElementById('custom-paper-width');
    const heightInput = document.getElementById('custom-paper-height');

    if (!unitSelect || !widthInput || !heightInput) return;

    const unit = unitSelect.value;
    if (unit === 'mm') {
      // Millimeters: whole numbers only
      widthInput.step = '1';
      heightInput.step = '1';
      widthInput.placeholder = 'Width (mm, whole number)';
      heightInput.placeholder = 'Height (mm, whole number)';
    } else if (unit === 'in') {
      // Inches: decimals allowed
      widthInput.step = '0.1';
      heightInput.step = '0.1';
      widthInput.placeholder = 'Width (in, e.g., 8.5)';
      heightInput.placeholder = 'Height (in, e.g., 11)';
    }
  }

  async loadSvgLibrary() {
    try {
      const response = await fetch('/api/list-svgs');
      const svgs = await response.json();
      const loaded = await Promise.all(svgs.map((svg) => this.prepareSvgLibraryEntry(svg)));
      this.svgLibrary = loaded.filter(Boolean);
      this.updateSvgLibraryList();
    } catch (error) {
      console.error('Error loading SVG library:', error);
    }
  }

  prepareSvgLibraryEntry(svgData) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => resolve({ ...svgData, previewImage: img });
      img.onerror = () => {
        console.warn('Failed to load preview for', svgData.filename);
        resolve({ ...svgData, previewImage: null });
      };
      img.src = svgData.preview_url;
    });
  }

  updateSvgLibraryList() {
    const list = document.getElementById('svg-library');
    if (!list) return;

    if (this.svgLibrary.length === 0) {
      list.innerHTML = `
        <div class="empty-state">
          ${lucideIconHTML('package', 32, '', 'opacity: 0.3;')}
          <p>No SVGs in library</p>
        </div>
      `;
      if (window.lucide) lucide.createIcons({ nodes: [list] });
      return;
    }

    list.innerHTML = this.svgLibrary
      .map(
        (svg) => {
          // Check if this SVG is assigned to any papers
          const assignedPapers = this.papers.filter(p => p.svg_id === svg.id);
          const assignedCount = assignedPapers.length;
          
          return `
        <div class="list-item" data-svg-id="${svg.id}">
          <div class="list-item-content">
            <div class="list-item-name">${this.escapeHtml(svg.filename)}</div>
            <div class="list-item-info">${svg.width.toFixed(1)}mm × ${svg.height.toFixed(1)}mm${assignedCount > 0 ? ` • Assigned to ${assignedCount} paper${assignedCount > 1 ? 's' : ''}` : ''}</div>
          </div>
          <div class="list-item-actions">
            <button class="icon-btn" data-action="remove-svg" title="Delete SVG" data-svg-id="${svg.id}">
              ${lucideIconHTML('trash-2', 14)}
            </button>
          </div>
        </div>
      `;
        }
      )
      .join('');

    list.querySelectorAll('.list-item').forEach((item) => {
      item.addEventListener('click', (e) => {
        // Don't trigger assignment if clicking on action buttons
        if (e.target.closest('.icon-btn')) return;

        const svgId = item.dataset.svgId;
        if (this.selectedPaperId) {
          this.assignSvgToPaper(svgId);
        }
      });
    });

    // Add delete button handlers
    list.querySelectorAll('[data-action="remove-svg"]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const svgId = btn.dataset.svgId;
        this.removeSvg(svgId);
      });
    });

    if (window.lucide) lucide.createIcons({ nodes: [list] });
  }

  async loadPapers() {
    try {
      const response = await fetch('/api/list-papers');
      const papers = await response.json();
      this.papers = papers.map((paper) => this.hydratePaper(paper));
      this.updatePaperList();
    } catch (error) {
      console.error('Error loading papers:', error);
    }
  }

  hydratePaper(paper) {
    const hydrated = { ...paper };
    if (hydrated.svg && hydrated.svg.id) {
      hydrated.svg_id = hydrated.svg.id;
    }
    return hydrated;
  }

  updatePaperList() {
    const list = document.getElementById('paper-list');
    if (!list) return;

    if (this.papers.length === 0) {
      list.innerHTML = `
        <div class="empty-state">
          ${lucideIconHTML('file-text', 32, '', 'opacity: 0.3;')}
          <p>No papers yet</p>
          <p class="empty-state-hint">Click + to add a paper</p>
        </div>
      `;
      if (window.lucide) lucide.createIcons({ nodes: [list] });
      return;
    }

    list.innerHTML = this.papers
      .map((paper) => {
        const name = paper.paper_name || 'Custom';
        const size = `${paper.paper_width.toFixed(0)}mm × ${paper.paper_height.toFixed(0)}mm`;
        const assigned = paper.svg_id ? `Assigned: ${this.getSvgFilename(paper.svg_id)}` : 'No SVG';
        const isSelected = paper.id === this.selectedPaperId || this.selectedPaperIds.has(paper.id);
        const lockHtml = paper.locked ? lucideIconHTML('lock', 12, '', 'margin-left: 4px; opacity: 0.7;') : '';
        return `
          <div class="list-item ${isSelected ? 'selected' : ''}" data-paper-id="${paper.id}">
            <div class="list-item-content">
              <div class="list-item-name">${this.escapeHtml(name)}${lockHtml}</div>
              <div class="list-item-info">${size} • ${assigned}</div>
            </div>
            <div class="list-item-actions">
              <button class="icon-btn" data-action="remove" title="Remove">
                ${lucideIconHTML('trash-2', 14)}
              </button>
            </div>
          </div>
        `;
      })
      .join('');

    list.querySelectorAll('.list-item').forEach((item) => {
      const paperId = item.dataset.paperId;
      if (!paperId) return;

      item.addEventListener('click', (e) => {
        if (e.target.closest('.icon-btn')) return;
        this.selectPaper(paperId);
      });

      const removeBtn = item.querySelector('[data-action="remove"]');
      if (removeBtn) {
        removeBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.removePaper(paperId);
        });
      }
    });

    if (window.lucide) lucide.createIcons({ nodes: [list] });
  }

  getSvgFilename(svgId) {
    const svg = this.svgLibrary.find((s) => s.id === svgId);
    return svg ? svg.filename : 'Unknown SVG';
  }

  selectPaper(paperId) {
    this.selectedPaperId = paperId;
    // Single click: clear multi-select (unless it's already in the set from shift-click)
    if (!this.selectedPaperIds.has(paperId)) {
      this.selectedPaperIds.clear();
    }
    this.refresh();
  }

  async removePaper(paperId) {
    if (paperId !== this.selectedPaperId) {
      const confirmed = await showConfirm('Remove Paper', 'Remove this paper?');
      if (!confirmed) return;
    }

    try {
      const response = await fetch(`/api/remove-paper/${paperId}`, { method: 'DELETE' });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to remove paper');
      }

      this.papers = this.papers.filter((p) => p.id !== paperId);
      if (this.selectedPaperId === paperId) {
        this.selectedPaperId = null;
      }
      this.selectedPaperIds.delete(paperId);
      this.refresh();
    } catch (error) {
      console.error('Error removing paper:', error);
      await showAlert('Error', 'Failed to remove paper: ' + error.message, 'error');
    }
  }

  async removeSelectedPaper() {
    const idsToRemove = this.selectedPaperIds.size > 0
      ? [...this.selectedPaperIds]
      : (this.selectedPaperId ? [this.selectedPaperId] : []);

    if (idsToRemove.length === 0) return;

    const msg = idsToRemove.length === 1
      ? 'Remove this paper?'
      : `Remove ${idsToRemove.length} selected papers?`;
    const confirmed = await showConfirm('Remove Paper', msg);
    if (!confirmed) return;

    for (const pid of idsToRemove) {
      try {
        const response = await fetch(`/api/remove-paper/${pid}`, { method: 'DELETE' });
        if (response.ok) {
          this.papers = this.papers.filter(p => p.id !== pid);
          this.selectedPaperIds.delete(pid);
          if (this.selectedPaperId === pid) this.selectedPaperId = null;
        }
      } catch (e) {
        console.error('Error removing paper:', e);
      }
    }
    this.refresh();
  }

  async alignPapers(action) {
    this._saveUndoSnapshot();
    try {
      const paperIds = this.selectedPaperIds.size > 0 ? [...this.selectedPaperIds] : [];
      const response = await fetch('/api/align-papers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, paper_ids: paperIds }),
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.error || 'Alignment failed');
      }
      const result = await response.json();
      for (const updatedPaper of (result.papers || [])) {
        const local = this.papers.find(p => p.id === updatedPaper.id);
        if (local) Object.assign(local, updatedPaper);
      }
      this.refresh();
      showToast(`Papers aligned: ${action.replace(/_/g, ' ')}`);
    } catch (e) {
      console.error('Alignment error:', e);
      await showAlert('Error', 'Alignment failed: ' + e.message, 'error');
    }
  }

  async removeSvg(svgId) {
    const svg = this.svgLibrary.find((s) => s.id === svgId);
    if (!svg) return;

    // Check if SVG is assigned to any papers
    const assignedPapers = this.papers.filter((p) => p.svg_id === svgId);
    const assignedCount = assignedPapers.length;

    // Build confirmation message
    let confirmMessage = `Are you sure you want to delete "${svg.filename}"?`;
    if (assignedCount > 0) {
      confirmMessage += `\n\nThis SVG is assigned to ${assignedCount} paper${assignedCount > 1 ? 's' : ''}. ${assignedCount > 1 ? 'Those papers' : 'That paper'} will be unassigned but kept on the canvas.`;
    }

    const confirmed = await showConfirm('Delete SVG', confirmMessage);
    if (!confirmed) return;

    try {
      const response = await fetch(`/api/remove-svg/${svgId}`, { method: 'DELETE' });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to remove SVG');
      }

      const result = await response.json();
      const unassignedPaperIds = result.unassigned_paper_ids || [];

      // Remove SVG from library
      this.svgLibrary = this.svgLibrary.filter((s) => s.id !== svgId);

      // Unassign papers that used this SVG
      for (const paper of this.papers) {
        if (unassignedPaperIds.includes(paper.id)) {
          paper.svg_id = null;
        }
      }

      // Update UI
      this.updateSvgLibraryList();
      this.refresh();
    } catch (error) {
      console.error('Error removing SVG:', error);
      await showAlert('Error', 'Failed to remove SVG: ' + error.message, 'error');
    }
  }

  updateInspector() {
    const content = document.getElementById('inspector-content');
    if (!content) return;

    // Item 22: multi-select summary
    if (this.selectedPaperIds.size > 1) {
      content.innerHTML = `
        <div class="empty-state">
          ${lucideIconHTML('layers', 32, '', 'opacity: 0.3;')}
          <p>${this.selectedPaperIds.size} papers selected</p>
          <p class="empty-state-hint">Shift+click to add/remove</p>
        </div>
        <div class="form-actions" style="margin-top: 1rem;">
          <button class="btn btn-danger btn-full" id="remove-multi-btn">Remove Selected</button>
        </div>
      `;
      document.getElementById('remove-multi-btn')?.addEventListener('click', () => this.removeSelectedPaper());
      if (window.lucide) lucide.createIcons({ nodes: [content] });
      return;
    }

    if (!this.selectedPaperId) {
      content.innerHTML = `
        <div class="empty-state">
          ${lucideIconHTML('sliders', 32, '', 'opacity: 0.3;')}
          <p>No paper selected</p>
          <p class="empty-state-hint">Select a paper to edit</p>
        </div>
      `;
      if (window.lucide) lucide.createIcons({ nodes: [content] });
      return;
    }

    const paper = this.papers.find((p) => p.id === this.selectedPaperId);
    if (!paper) return;

    const isLocked = !!paper.locked;
    const lockIcon = isLocked ? 'lock' : 'unlock';
    const lockTitle = isLocked ? 'Unlock paper' : 'Lock paper';

    content.innerHTML = `
      <div class="form-group">
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <label>Paper Size</label>
          <button class="icon-btn" id="lock-paper-btn" title="${lockTitle}" style="color: ${isLocked ? 'var(--accent)' : 'inherit'}">
            <i data-lucide="${lockIcon}" style="width: 14px; height: 14px;"></i>
          </button>
        </div>
        <div class="info-value" style="margin-top: 0.25rem">
          ${paper.paper_name || 'Custom'} (${paper.paper_width.toFixed(0)} × ${paper.paper_height.toFixed(0)}mm)
        </div>
      </div>

      <div class="form-group">
        <label>Assign SVG</label>
        <select id="inspector-assign-svg" class="input-select" style="margin-top: 0.5rem" ${isLocked ? 'disabled' : ''}>
          <option value="">None</option>
          ${this.svgLibrary.map(svg => `
            <option value="${svg.id}" ${paper.svg_id === svg.id ? 'selected' : ''}>
              ${this.escapeHtml(svg.filename)} (${svg.width.toFixed(0)}×${svg.height.toFixed(0)}mm)
            </option>
          `).join('')}
        </select>
      </div>

      <div class="form-group">
        <label>Transform</label>
        <div class="transform-grid" style="margin-top: 0.5rem">
          <div class="input-group">
            <input type="number" id="inspector-x" class="input-number" value="${paper.x ?? 0}" step="0.1" ${isLocked ? 'disabled' : ''} />
            <span class="input-unit">mm</span>
          </div>
          <div class="input-group">
            <input type="number" id="inspector-y" class="input-number" value="${paper.y ?? 0}" step="0.1" ${isLocked ? 'disabled' : ''} />
            <span class="input-unit">mm</span>
          </div>
        </div>
        <div class="transform-grid" style="margin-top: 0.75rem">
          <div class="input-group">
            <input type="number" id="inspector-rotation" class="input-number" value="${paper.rotation ?? 0}" step="90" ${isLocked ? 'disabled' : ''} />
            <span class="input-unit">°</span>
          </div>
          <div style="display: flex; gap: 0.5rem">
            <button class="btn btn-secondary" id="rotate-left-btn" style="flex: 1" ${isLocked ? 'disabled' : ''}>↺ Left</button>
            <button class="btn btn-secondary" id="rotate-right-btn" style="flex: 1" ${isLocked ? 'disabled' : ''}>↻ Right</button>
          </div>
        </div>
      </div>

      <div class="form-actions">
        <button class="btn btn-secondary btn-full" id="clone-paper-btn">Clone Paper</button>
        <button class="btn btn-danger btn-full" id="remove-paper-inspector-btn">Remove Paper</button>
      </div>
    `;

    // Lock toggle (Item 24)
    document.getElementById('lock-paper-btn')?.addEventListener('click', () => {
      this.togglePaperLock(this.selectedPaperId);
    });

    // Event listeners for inspector controls
    const assignSelect = document.getElementById('inspector-assign-svg');
    assignSelect?.addEventListener('change', (e) => {
      this.assignSvgToPaper(e.target.value || null);
    });

    const xInput = document.getElementById('inspector-x');
    const yInput = document.getElementById('inspector-y');
    const rotationInput = document.getElementById('inspector-rotation');

    // Item 5: debounced input handlers
    const debouncedX = this._debounce((v) => this.updatePaperPosition('x', v));
    const debouncedY = this._debounce((v) => this.updatePaperPosition('y', v));
    const debouncedR = this._debounce((v) => this.updatePaperRotation(Number(v)));

    xInput?.addEventListener('input', (e) => debouncedX(e.target.value));
    yInput?.addEventListener('input', (e) => debouncedY(e.target.value));
    rotationInput?.addEventListener('input', (e) => debouncedR(e.target.value));

    document.getElementById('rotate-left-btn')?.addEventListener('click', () => {
      this.rotateSelectedPaper(-90);
    });

    document.getElementById('rotate-right-btn')?.addEventListener('click', () => {
      this.rotateSelectedPaper(90);
    });

    document.getElementById('clone-paper-btn')?.addEventListener('click', () => {
      this.cloneSelectedPaper();
    });

    document.getElementById('remove-paper-inspector-btn')?.addEventListener('click', () => {
      this.removePaper(this.selectedPaperId);
    });

    if (window.lucide) lucide.createIcons({ nodes: [content] });
  }

  async addSvg(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/api/add-svg', { method: 'POST', body: formData });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to add SVG');
      }

      const svgData = await response.json();
      const entry = await this.prepareSvgLibraryEntry(svgData);
      this.svgLibrary.push(entry);
      this.updateSvgLibraryList();
      this.refresh({ paperList: false });
      showToast(`SVG added: ${svgData.filename}`);
    } catch (error) {
      console.error('Error adding SVG:', error);
      await showAlert('Error', 'Failed to add SVG: ' + error.message, 'error');
    }
  }

  async addPaperFromSelect() {
    const select = document.getElementById('add-paper-select');
    if (!select || !select.value) {
      await showAlert('No Paper Selected', 'Please select a paper size first.', 'warning');
      return;
    }

    let requestBody;

    if (select.value === 'custom') {
      // Handle custom paper size
      const unit = document.getElementById('custom-paper-unit')?.value || 'mm';
      const widthInput = document.getElementById('custom-paper-width');
      const heightInput = document.getElementById('custom-paper-height');

      if (!widthInput || !heightInput) {
        await showAlert('Error', 'Custom paper inputs not found.', 'error');
        return;
      }

      let width = parseFloat(widthInput.value);
      let height = parseFloat(heightInput.value);

      if (isNaN(width) || isNaN(height) || width <= 0 || height <= 0) {
        await showAlert('Invalid Input', 'Please enter valid width and height values.', 'warning');
        return;
      }

      // Validate based on unit
      if (unit === 'mm') {
        // Millimeters must be whole numbers
        if (!Number.isInteger(width) || !Number.isInteger(height)) {
          await showAlert('Invalid Input', 'Millimeters must be whole numbers.', 'warning');
          return;
        }
      } else if (unit === 'in') {
        // Inches can be decimals (already handled by parseFloat)
        // Validate that we have valid decimal numbers
        if (!Number.isFinite(width) || !Number.isFinite(height)) {
          await showAlert('Invalid Input', 'Please enter valid decimal numbers for inches.', 'warning');
          return;
        }
        // Convert inches to millimeters (1 inch = 25.4 mm)
        width = width * 25.4;
        height = height * 25.4;
      }

      requestBody = {
        paper_name: 'custom',
        paper_width: width,
        paper_height: height,
      };
    } else {
      // Handle predefined paper sizes
      const [paperName, orientation] = select.value.split('_');
      requestBody = {
        paper_name: paperName,
        orientation,
      };
    }

    try {
      const response = await fetch('/api/add-paper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to add paper');
      }

      const paper = await response.json();
      this.papers.push(paper);
      this.selectPaper(paper.id);
      this.refresh({ inspector: false });

      // Close modal and reset form
      this.closePaperModal();
      showToast('Paper added');
    } catch (error) {
      console.error('Error adding paper:', error);
      await showAlert('Error', 'Failed to add paper: ' + error.message, 'error');
    }
  }

  closePaperModal() {
    const modal = document.getElementById('paper-modal');
    const select = document.getElementById('add-paper-select');
    const widthInput = document.getElementById('custom-paper-width');
    const heightInput = document.getElementById('custom-paper-height');

    if (modal) modal.classList.remove('active');
    if (select) select.value = '';
    this.toggleCustomPaperInputs(false);
    if (widthInput) widthInput.value = '';
    if (heightInput) heightInput.value = '';
  }

  async updatePaperPosition(axis, value, paperId = null) {
    const targetId = paperId || this.selectedPaperId;
    if (!targetId) return;

    const paper = this.papers.find((p) => p.id === targetId);
    if (!paper) return;

    if (value === '' || value === null || value === undefined) return;

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) return;

    paper[axis] = numericValue;
    this.render();

    try {
      const response = await fetch('/api/update-paper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: paper.id,
          x: Number.isFinite(paper.x) ? paper.x : 0,
          y: Number.isFinite(paper.y) ? paper.y : 0,
        }),
      });

      if (response.ok) {
        const result = await response.json();
        Object.assign(paper, result.paper);
      }
    } catch (error) {
      console.error('Error updating paper position:', error);
    }
  }

  async updatePaperRotation(rotation) {
    if (!this.selectedPaperId) return;

    const paper = this.papers.find((p) => p.id === this.selectedPaperId);
    if (!paper) return;

    paper.rotation = rotation;
    this.render();

    try {
      const response = await fetch('/api/update-paper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: paper.id, rotation }),
      });

      if (response.ok) {
        const result = await response.json();
        Object.assign(paper, result.paper);
        this.updateInspector();
      }
    } catch (error) {
      console.error('Error updating rotation:', error);
    }
  }

  async rotateSelectedPaper(delta) {
    if (!this.selectedPaperId) return;

    const paper = this.papers.find((p) => p.id === this.selectedPaperId);
    if (!paper) return;

    const currentRotation = paper.rotation || 0;
    const newRotation = (currentRotation + delta + 360) % 360;

    await this.updatePaperRotation(newRotation);
  }

  async togglePaperLock(paperId) {
    const paper = this.papers.find(p => p.id === paperId);
    if (!paper) return;
    const newLocked = !paper.locked;
    paper.locked = newLocked;
    try {
      await fetch('/api/update-paper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: paperId, locked: newLocked }),
      });
    } catch (e) {
      console.error('Error toggling lock:', e);
    }
    this.refresh();
  }

  async assignSvgToPaper(svgId) {
    if (!this.selectedPaperId) return;

    const paper = this.papers.find((p) => p.id === this.selectedPaperId);
    if (!paper) return;

    paper.svg_id = svgId || null;
    this.render();

    try {
      const response = await fetch('/api/update-paper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: paper.id, svg_id: paper.svg_id }),
      });

      if (response.ok) {
        const result = await response.json();
        Object.assign(paper, result.paper);
        this.updatePaperList();
        this.updateInspector();
        this.render();
      }
    } catch (error) {
      console.error('Error assigning SVG:', error);
    }
  }

  async cloneSelectedPaper() {
    if (!this.selectedPaperId) return;

    try {
      const response = await fetch(`/api/clone-paper/${this.selectedPaperId}`, { method: 'POST' });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to clone paper');
      }

      const paper = await response.json();
      this.papers.push(paper);
      this.selectPaper(paper.id);
      this.refresh({ inspector: false });
      showToast('Paper cloned');
    } catch (error) {
      console.error('Error cloning paper:', error);
      await showAlert('Error', 'Failed to clone paper: ' + error.message, 'error');
    }
  }

  async autoArrange() {
    try {
      const response = await fetch('/api/auto-arrange', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Auto-arrange failed');
      }

      const result = await response.json();
      const updated = result.papers || [];

      for (const updatedPaper of updated) {
        const local = this.papers.find((p) => p.id === updatedPaper.id);
        if (local) {
          Object.assign(local, updatedPaper);
        }
      }

      this.refresh();
      showToast('Papers auto-arranged');
    } catch (error) {
      console.error('Auto-arrange error:', error);
      await showAlert('Error', 'Auto-arrange failed: ' + error.message, 'error');
    }
  }

  updateAutoAssignVisibility() {
    const autoAssignBtn = document.getElementById('auto-assign-btn');
    if (!autoAssignBtn) return;
    const paperCount = this.papers.length;
    const svgCount = this.svgLibrary.length;
    const shouldShow = paperCount > 0 && svgCount > 0 && paperCount === svgCount;
    autoAssignBtn.style.display = shouldShow ? 'flex' : 'none';
  }

  async autoAssignSvgs() {
    try {
      const response = await fetch('/api/auto-assign-svgs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Auto assign failed');
      }

      const result = await response.json();
      const updated = result.papers || [];
      for (const updatedPaper of updated) {
        const local = this.papers.find((p) => p.id === updatedPaper.id);
        if (local) Object.assign(local, updatedPaper);
      }
      this.refresh();
      showToast('SVGs auto-assigned to papers');
    } catch (error) {
      console.error('Auto-assign error:', error);
      await showAlert('Error', 'Auto assign failed: ' + error.message, 'error');
    }
  }

  getCanvasPoint(event) {
    // getBoundingClientRect() already accounts for CSS transforms
    const canvasRect = this.canvas.getBoundingClientRect();
    
    // Get mouse position relative to canvas
    const mouseX = event.clientX - canvasRect.left;
    const mouseY = event.clientY - canvasRect.top;
    
    // Convert to canvas pixel coordinates
    const scaleX = this.canvas.width / canvasRect.width;
    const scaleY = this.canvas.height / canvasRect.height;
    
    const canvasX = mouseX * scaleX;
    const canvasY = mouseY * scaleY;
    
    // Convert to mm (divide by pixels-per-mm scale)
    return {
      x: canvasX / this.scale,
      y: canvasY / this.scale,
    };
  }

  getPaperBounds(paper) {
    return {
      minX: paper.x || 0,
      minY: paper.y || 0,
      maxX: (paper.x || 0) + (paper.paper_width || 0),
      maxY: (paper.y || 0) + (paper.paper_height || 0),
    };
  }

  paperAtPoint(point) {
    for (let i = this.papers.length - 1; i >= 0; i -= 1) {
      const paper = this.papers[i];
      const bounds = this.getPaperBounds(paper);
      if (point.x >= bounds.minX && point.x <= bounds.maxX && point.y >= bounds.minY && point.y <= bounds.maxY) {
        return paper;
      }
    }
    return null;
  }

  onMouseDown(event) {
    const point = this.getCanvasPoint(event);

    if (this.activeTool === 'pan' || this.panning) {
      this.panning = true;
      this.dragStart = { x: event.clientX, y: event.clientY };
      this.dragStartTransform = { ...this.canvasTransform };
      this.canvas.style.cursor = 'grabbing';
      return;
    }

    const hitPaper = this.paperAtPoint(point);

    if (hitPaper) {
      if (event.shiftKey) {
        // Item 22: Shift+click adds/removes from multi-select
        if (this.selectedPaperIds.has(hitPaper.id)) {
          this.selectedPaperIds.delete(hitPaper.id);
          if (this.selectedPaperId === hitPaper.id) {
            this.selectedPaperId = this.selectedPaperIds.size > 0 ? [...this.selectedPaperIds][0] : null;
          }
        } else {
          // Add current primary to set first
          if (this.selectedPaperId) this.selectedPaperIds.add(this.selectedPaperId);
          this.selectedPaperIds.add(hitPaper.id);
          this.selectedPaperId = hitPaper.id;
        }
        this.refresh();
      } else {
        // Single click: clear multi-select, select this paper
        if (!this.selectedPaperIds.has(hitPaper.id)) {
          this.selectedPaperIds.clear();
        }
        this.selectPaper(hitPaper.id);
      }

      if (!hitPaper.locked) {
        this.dragging = true;
        this.dragStart = point;
        this.dragStartTransform = { x: hitPaper.x || 0, y: hitPaper.y || 0 };
        // Item 22: save start positions for all selected papers
        this.dragStartPositions = {};
        const idsToMove = this.selectedPaperIds.size > 0 ? [...this.selectedPaperIds] : [hitPaper.id];
        for (const pid of idsToMove) {
          const p = this.papers.find(pp => pp.id === pid);
          if (p) this.dragStartPositions[pid] = { x: p.x || 0, y: p.y || 0 };
        }
        event.preventDefault();
      }
    } else {
      this.selectedPaperId = null;
      this.selectedPaperIds.clear();
      this.refresh();
    }
  }

  onMouseMove(event) {
    // Item 27: store last mouse event for zoom coordinate update
    this.lastMouseEvent = event;

    // Item 6: merged coordinate label update
    const point = this.getCanvasPoint(event);
    const mouseLabel = document.getElementById('mouse-position');
    if (mouseLabel) {
      mouseLabel.textContent = `${point.x.toFixed(1)}mm, ${point.y.toFixed(1)}mm`;
    }

    if (this.panning) {
      const dx = event.clientX - this.dragStart.x;
      const dy = event.clientY - this.dragStart.y;
      this.canvasTransform.x = this.dragStartTransform.x + dx;
      this.canvasTransform.y = this.dragStartTransform.y + dy;
      this.render();
      return;
    }

    if (!this.dragging || !this.selectedPaperId) return;

    const paper = this.papers.find((p) => p.id === this.selectedPaperId);
    if (!paper) return;

    const dx = point.x - this.dragStart.x;
    const dy = point.y - this.dragStart.y;

    // Item 22: move all selected papers together when dragging
    const idsToMove = this.selectedPaperIds.size > 0 ? [...this.selectedPaperIds] : [this.selectedPaperId];
    for (const pid of idsToMove) {
      const p = this.papers.find(pp => pp.id === pid);
      if (!p || p.locked) continue;
      const startPos = this.dragStartPositions[pid];
      if (!startPos) continue;
      let newX = startPos.x + dx;
      let newY = startPos.y + dy;
      // Item 21: snap to grid
      if (this.snapToGrid) {
        newX = Math.round(newX / 10) * 10;
        newY = Math.round(newY / 10) * 10;
      }
      p.x = newX;
      p.y = newY;
    }

    // Update inspector inputs for primary selected paper
    const xInput = document.getElementById('inspector-x');
    const yInput = document.getElementById('inspector-y');
    if (xInput) xInput.value = paper.x.toFixed(1);
    if (yInput) yInput.value = paper.y.toFixed(1);

    this.render();
  }

  async onMouseUp() {
    if (this.panning) {
      this.panning = false;
      this.canvas.style.cursor = this.activeTool === 'pan' ? 'grab' : 'crosshair';
      return;
    }

    if (this.dragging && this.selectedPaperId) {
      // Item 22: update all selected papers' positions
      const idsToUpdate = this.selectedPaperIds.size > 0 ? [...this.selectedPaperIds] : [this.selectedPaperId];
      for (const pid of idsToUpdate) {
        const p = this.papers.find(pp => pp.id === pid);
        if (p) {
          await this.updatePaperPosition('x', p.x, pid);
          await this.updatePaperPosition('y', p.y, pid);
        }
      }
    }

    this.dragging = false;
    this.dragStartTransform = null;
    this.dragStartPositions = {};
  }

  render() {
    // Apply CSS transform only to canvas element for pan/zoom
    // This keeps the dark background and grid pattern fixed, only moving the white canvas and content
    if (this.canvas) {
      this.canvas.style.transform = `translate(${this.canvasTransform.x}px, ${this.canvasTransform.y}px) scale(${this.canvasTransform.scale})`;
      this.canvas.style.transformOrigin = 'center center';
    }

    // Clear canvas
    this.ctx.fillStyle = '#ffffff';
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    // Draw grid (moves with container transform)
    this.drawGrid();

    // Draw papers (move with container transform)
    for (const paper of this.papers) {
      this.drawPaper(paper);
    }
  }

  drawGrid() {
    const gridSizePx = 10 * this.scale;

    if (this.snapToGrid) {
      // Item 21: prominent snap-to-grid lines (dotted, slightly more visible)
      this.ctx.strokeStyle = 'rgba(100, 149, 237, 0.35)';
      this.ctx.lineWidth = 1;
      this.ctx.setLineDash([2, 4]);
    } else {
      this.ctx.strokeStyle = '#e0e0e0';
      this.ctx.lineWidth = 1;
      this.ctx.setLineDash([]);
    }

    for (let x = 0; x <= this.canvasWidth * this.scale; x += gridSizePx) {
      this.ctx.beginPath();
      this.ctx.moveTo(x, 0);
      this.ctx.lineTo(x, this.canvas.height);
      this.ctx.stroke();
    }

    for (let y = 0; y <= this.canvasHeight * this.scale; y += gridSizePx) {
      this.ctx.beginPath();
      this.ctx.moveTo(0, y);
      this.ctx.lineTo(this.canvas.width, y);
      this.ctx.stroke();
    }

    this.ctx.setLineDash([]);
  }

  drawPaper(paper) {
    const x = (paper.x || 0) * this.scale;
    const y = (paper.y || 0) * this.scale;
    const width = (paper.paper_width || 0) * this.scale;
    const height = (paper.paper_height || 0) * this.scale;
    const rotation = (paper.rotation || 0) * (Math.PI / 180);

    const centerX = x + width / 2;
    const centerY = y + height / 2;

    this.ctx.save();
    this.ctx.translate(centerX, centerY);
    this.ctx.rotate(rotation);

    // Paper outline
    this.ctx.strokeStyle = '#ffaa00';
    this.ctx.lineWidth = 2 / this.scale;
    this.ctx.setLineDash([10 / this.scale, 5 / this.scale]);
    this.ctx.strokeRect(-width / 2, -height / 2, width, height);
    this.ctx.setLineDash([]);

    // Selection highlight (single or multi-select)
    const isSelected = paper.id === this.selectedPaperId || this.selectedPaperIds.has(paper.id);
    if (isSelected) {
      this.ctx.strokeStyle = '#00E5FF';
      this.ctx.lineWidth = 3 / this.scale;
      this.ctx.setLineDash([5 / this.scale, 5 / this.scale]);
      this.ctx.strokeRect(-width / 2, -height / 2, width, height);
      this.ctx.setLineDash([]);
    }

    // Lock icon indicator (Item 24)
    if (paper.locked) {
      this.ctx.fillStyle = 'rgba(255, 200, 0, 0.85)';
      this.ctx.font = `${12 / this.canvasTransform.scale}px sans-serif`;
      this.ctx.fillText('🔒', -width / 2 + 4, -height / 2 + 14 / this.canvasTransform.scale);
    }

    // SVG preview
    if (paper.svg_id) {
      const svg = this.svgLibrary.find((s) => s.id === paper.svg_id);
      if (svg && svg.previewImage) {
        const scale = paper.svg_scale || 1.0;
        const scaledWidth = svg.width * scale * this.scale;
        const scaledHeight = svg.height * scale * this.scale;
        const svgX = -scaledWidth / 2;
        const svgY = -scaledHeight / 2;
        this.ctx.drawImage(svg.previewImage, svgX, svgY, scaledWidth, scaledHeight);
      }
    }

    this.ctx.restore();
  }

  checkPapersOutsideCanvas() {
    const papersOutside = [];
    
    for (const paper of this.papers) {
      const x = paper.x || 0;
      const y = paper.y || 0;
      const width = paper.paper_width || 0;
      const height = paper.paper_height || 0;
      const rotation = (paper.rotation || 0) * (Math.PI / 180);
      
      // Calculate paper corners (before rotation, relative to paper center)
      const halfWidth = width / 2;
      const halfHeight = height / 2;
      const centerX = x + halfWidth;
      const centerY = y + halfHeight;
      
      // Paper corners in local coordinates (relative to center)
      const corners = [
        [-halfWidth, -halfHeight], // top-left
        [halfWidth, -halfHeight],  // top-right
        [halfWidth, halfHeight],    // bottom-right
        [-halfWidth, halfHeight]    // bottom-left
      ];
      
      // Rotate corners and convert to canvas coordinates
      const cosR = Math.cos(rotation);
      const sinR = Math.sin(rotation);
      let isOutside = false;
      
      for (const [localX, localY] of corners) {
        // Rotate around origin
        const rotatedX = localX * cosR - localY * sinR;
        const rotatedY = localX * sinR + localY * cosR;
        
        // Translate to canvas position
        const canvasX = centerX + rotatedX;
        const canvasY = centerY + rotatedY;
        
        // Check if corner is outside canvas boundaries
        if (canvasX < 0 || canvasX > this.canvasWidth || 
            canvasY < 0 || canvasY > this.canvasHeight) {
          isOutside = true;
          break;
        }
      }
      
      if (isOutside) {
        const paperName = paper.paper_name || 'Custom';
        papersOutside.push(`${paperName} (${width.toFixed(0)}×${height.toFixed(0)}mm)`);
      }
    }
    
    return papersOutside;
  }

  async export() {
    if (this.papers.length === 0) {
      await showAlert('No Papers', 'No papers to export', 'warning');
      return;
    }

    // Check if any papers are outside the canvas
    const papersOutside = this.checkPapersOutsideCanvas();
    if (papersOutside.length > 0) {
      const paperList = papersOutside.join('\n• ');
      const message = `Some papers are outside the canvas boundaries:\n\n• ${paperList}\n\nAre you okay with this? The export will proceed anyway.`;
      await showAlert('Papers Outside Canvas', message, 'warning');
    }

    const exportBtn = document.getElementById('export-btn');
    const exportText = document.getElementById('export-btn-text');
    const exportSpinner = document.getElementById('export-btn-spinner');

    // Create AbortController for cancelling fetch requests
    const abortController = new AbortController();
    this.exportAbortController = abortController;

    try {
      exportBtn.disabled = true;
      exportText.textContent = 'Exporting...';
      exportSpinner.style.display = 'inline-block';

      let outputFolder = null;
      let userCancelled = false;

      // Try folder picker first
      try {
        const pickerResponse = await fetch('/api/select-output-folder', {
          method: 'POST',
          signal: abortController.signal
        });
        
        if (pickerResponse.ok) {
          const pickerResult = await pickerResponse.json();
          outputFolder = pickerResult.output_folder || null;
        } else {
          // Check if it was cancelled
          try {
            const errorData = await pickerResponse.json();
            if (errorData.error && (errorData.error.toLowerCase().includes('cancel') || errorData.error.toLowerCase().includes('canceled'))) {
              userCancelled = true;
            }
          } catch (e) {
            // If we can't parse the error, assume it might be a cancellation
            // But don't set userCancelled to true, fall through to prompt
          }
        }
      } catch (error) {
        // Check if it was aborted
        if (error.name === 'AbortError') {
          userCancelled = true;
        }
        // Other errors (like network errors), fall back to prompt
      }

      // If folder picker was cancelled, abort export
      if (userCancelled) {
        exportBtn.disabled = false;
        exportText.textContent = 'Export';
        exportSpinner.style.display = 'none';
        this.exportAbortController = null;
        return;
      }

      // Fall back to prompt if no folder selected
      if (!outputFolder) {
        outputFolder = prompt('Enter output folder path (or leave empty for temp folder):');
        // If prompt returns null, user cancelled
        if (outputFolder === null) {
          exportBtn.disabled = false;
          exportText.textContent = 'Export';
          exportSpinner.style.display = 'none';
          this.exportAbortController = null;
          return;
        }
      }

      // Proceed with export
      const response = await fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_folder: outputFolder || null }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Export failed');
      }

      const result = await response.json();
      showToast(`Exported to: ${result.output_folder}`, 'success', 5000);
    } catch (error) {
      // Don't show error if user cancelled
      if (error.name === 'AbortError') {
        // User cancelled, silently reset button
      } else {
        console.error('Export error:', error);
        await showAlert('Export Failed', 'Export failed: ' + error.message, 'error');
      }
    } finally {
      exportBtn.disabled = false;
      exportText.textContent = 'Export';
      exportSpinner.style.display = 'none';
      this.exportAbortController = null;
    }
  }

  async clearAll() {
    const paperCount = this.papers.length;
    const svgCount = this.svgLibrary.length;
    
    if (paperCount === 0 && svgCount === 0) {
      await showAlert('Nothing to Clear', 'There are no papers or SVGs to clear.', 'info');
      return;
    }

    // Build confirmation message
    const parts = [];
    if (paperCount > 0) {
      parts.push(`${paperCount} paper${paperCount > 1 ? 's' : ''}`);
    }
    if (svgCount > 0) {
      parts.push(`${svgCount} SVG${svgCount > 1 ? 's' : ''}`);
    }
    const message = `Are you sure you want to clear everything?\n\nThis will remove:\n• ${parts.join('\n• ')}\n\nThis action cannot be undone.`;

    const confirmed = await showConfirm('Clear All', message);
    if (!confirmed) return;

    try {
      const response = await fetch('/api/clear-all', { method: 'POST' });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to clear all');
      }

      const result = await response.json();

      // Clear local state
      this.papers = [];
      this.svgLibrary = [];
      this.selectedPaperId = null;
      this.selectedPaperIds.clear();

      // Update UI
      this.updateSvgLibraryList();
      this.refresh();

      showToast(`Cleared ${result.papers_removed} paper${result.papers_removed !== 1 ? 's' : ''} and ${result.svgs_removed} SVG${result.svgs_removed !== 1 ? 's' : ''}`);
    } catch (error) {
      console.error('Error clearing all:', error);
      await showAlert('Error', 'Failed to clear all: ' + error.message, 'error');
    }
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // --- Surface Calibration ---

  setupCalibration() {
    this.calSamplePoints = null;
    this.calSampleNx = 0;
    this.calSampleNy = 0;
    this.cal3dRotX = -0.6;
    this.cal3dRotZ = 0.5;

    document.getElementById('open-calibration-btn')?.addEventListener('click', () => this.openCalibrationModal());
    const calModal = document.getElementById('calibration-modal');
    document.getElementById('close-calibration-btn')?.addEventListener('click', () => calModal?.classList.remove('active'));
    calModal?.addEventListener('click', (e) => { if (e.target === calModal) calModal.classList.remove('active'); });

    // Tabs
    document.querySelectorAll('.cal-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.cal-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.cal-tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(`cal-tab-${tab.getAttribute('data-cal-tab')}`)?.classList.add('active');
        if (tab.getAttribute('data-cal-tab') === 'view') this.calViewLoad();
      });
    });

    // Grid tab
    const gridSpacing = document.getElementById('cal-grid-spacing');
    gridSpacing?.addEventListener('change', () => this.updateCalGridInfo());
    gridSpacing?.addEventListener('input', () => this.updateCalGridInfo());
    document.getElementById('cal-grid-apply-map')?.addEventListener('change', (e) => {
      document.getElementById('cal-grid-map-path-group').style.display = e.target.checked ? 'block' : 'none';
    });
    document.getElementById('cal-grid-generate-btn')?.addEventListener('click', () => this.calGenerateGrid());

    // Sample tab
    document.getElementById('cal-sample-spacing')?.addEventListener('change', () => this.calBuildSampleGrid());
    document.getElementById('cal-sample-load-btn')?.addEventListener('click', () => this.calLoadSavedMap());
    document.getElementById('cal-sample-reset-btn')?.addEventListener('click', () => {
      if (this.calSamplePoints) {
        for (let i = 0; i < this.calSampleNy; i++)
          for (let j = 0; j < this.calSampleNx; j++)
            this.calSamplePoints[i][j] = 0;
        this.calRenderSampleGrid();
      }
    });
    document.getElementById('cal-sample-save-btn')?.addEventListener('click', () => this.calSaveMap());

    // View tab
    document.getElementById('cal-view-delete-btn')?.addEventListener('click', () => this.calDeleteMap());
    this.setup3dCanvasDrag();
    this.updateHeightMapIndicator();
  }

  openCalibrationModal() {
    const modal = document.getElementById('calibration-modal');
    if (!modal) return;
    modal.classList.add('active');
    if (window.lucide) lucide.createIcons({ nodes: [modal] });
    this.updateCalGridInfo();
    if (!this.calSamplePoints) this.calBuildSampleGrid();
  }

  async updateHeightMapIndicator() {
    try {
      const response = await fetch('/api/settings');
      if (!response.ok) throw new Error('Failed to load calibration status');
      const settings = await response.json();
      this.settings = { ...this.settings, ...settings };
      this.updateCalibrationStatusUI(this.settings);
    } catch (error) {
      console.error('Failed to update calibration status:', error);
      this.updateCalibrationStatusUI({ height_map_will_apply: false });
    }
  }

  async updateCalGridInfo() {
    const spacing = parseFloat(document.getElementById('cal-grid-spacing')?.value) || 30;
    try {
      const resp = await fetch(`/api/surface-cal/grid-info?spacing=${spacing}`);
      const data = await resp.json();
      const el = document.getElementById('cal-grid-info');
      if (el) el.textContent = `${data.nx} × ${data.ny} = ${data.nx * data.ny} sample points on ${data.area_width}×${data.area_height}mm bed`;
    } catch (e) { /* ignore */ }
  }

  async calGenerateGrid() {
    const spacing = parseFloat(document.getElementById('cal-grid-spacing')?.value) || 30;
    const crossSize = parseFloat(document.getElementById('cal-grid-cross-size')?.value) || 4;
    const applyMap = document.getElementById('cal-grid-apply-map')?.checked;
    const folder = await this.pickFolder();
    if (!folder) return;
    try {
      const resp = await fetch('/api/surface-cal/grid', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_folder: folder, spacing, cross_size: crossSize, apply_map: applyMap }),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.error);
      showToast(`Grid G-code saved: ${result.path.split('/').pop()}`, 'success', 4000);
    } catch (e) {
      await showAlert('Error', 'Failed to generate grid: ' + e.message, 'error');
    }
  }

  async calBuildSampleGrid() {
    const spacing = parseFloat(document.getElementById('cal-sample-spacing')?.value) || 30;
    try {
      const resp = await fetch(`/api/surface-cal/grid-info?spacing=${spacing}`);
      const data = await resp.json();
      this.calSampleNx = data.nx;
      this.calSampleNy = data.ny;
      this.calSampleXCoords = data.x_coords;
      this.calSampleYCoords = data.y_coords;
      this.calSampleAreaW = data.area_width;
      this.calSampleAreaH = data.area_height;
      if (!this.calSamplePoints || this.calSamplePoints.length !== data.ny ||
          (this.calSamplePoints[0] && this.calSamplePoints[0].length !== data.nx)) {
        this.calSamplePoints = Array.from({ length: data.ny }, () => Array(data.nx).fill(0));
      }
      this.calRenderSampleGrid();
    } catch (e) { /* ignore */ }
  }

  calRenderSampleGrid() {
    const container = document.getElementById('cal-sample-grid');
    if (!container) return;
    const deltaZ = parseFloat(document.getElementById('cal-sample-delta-z')?.value) || 0.2;
    container.style.gridTemplateColumns = `32px repeat(${this.calSampleNx}, 44px)`;
    container.innerHTML = '';
    const corner = document.createElement('div');
    corner.style.cssText = 'width:32px;height:44px;';
    container.appendChild(corner);
    for (let j = 0; j < this.calSampleNx; j++) {
      const l = document.createElement('div');
      l.className = 'cal-grid-axis-label';
      l.textContent = this.calSampleXCoords[j].toFixed(0);
      container.appendChild(l);
    }
    for (let i = 0; i < this.calSampleNy; i++) {
      const yl = document.createElement('div');
      yl.className = 'cal-grid-axis-label';
      yl.textContent = this.calSampleYCoords[i].toFixed(0);
      container.appendChild(yl);
      for (let j = 0; j < this.calSampleNx; j++) {
        const level = this.calSamplePoints[i][j];
        const mm = level * deltaZ;
        const cell = document.createElement('div');
        cell.className = `cal-cell ${level > 0 ? 'cal-positive' : level < 0 ? 'cal-negative' : 'cal-zero'}`;
        cell.innerHTML = `<span class="cal-cell-level">${level > 0 ? '+' : ''}${level}</span><span class="cal-cell-mm">${mm >= 0 ? '+' : ''}${mm.toFixed(2)}</span>`;
        cell.title = `Row ${i} Col ${j} — Click: +1, Shift+Click: -1`;
        cell.addEventListener('click', (e) => {
          this.calSamplePoints[i][j] += e.shiftKey ? -1 : 1;
          this.calRenderSampleGrid();
        });
        container.appendChild(cell);
      }
    }
  }

  async calLoadSavedMap() {
    try {
      const resp = await fetch('/api/surface-cal/map');
      const data = await resp.json();
      if (!data.exists) { await showAlert('No Map', 'No saved height map yet.', 'info'); return; }
      document.getElementById('cal-sample-spacing').value = data.grid_spacing;
      document.getElementById('cal-sample-delta-z').value = data.delta_z_mm;
      document.getElementById('cal-sample-name').value = data.name || '';
      document.getElementById('cal-sample-paper').value = data.paper || '';
      document.getElementById('cal-sample-plotter').value = data.plotter || '';
      document.getElementById('cal-sample-pen').value = data.pen || '';
      this.calSampleNx = data.nx;
      this.calSampleNy = data.ny;
      const infoResp = await fetch(`/api/surface-cal/grid-info?spacing=${data.grid_spacing}`);
      const infoData = await infoResp.json();
      this.calSampleXCoords = infoData.x_coords;
      this.calSampleYCoords = infoData.y_coords;
      this.calSampleAreaW = infoData.area_width;
      this.calSampleAreaH = infoData.area_height;
      this.calSamplePoints = data.points.map(row => row.map(v => parseInt(v)));
      this.calRenderSampleGrid();
      showToast('Map loaded for refinement', 'success');
    } catch (e) {
      await showAlert('Error', 'Failed to load map: ' + e.message, 'error');
    }
  }

  async calSaveMap() {
    if (!this.calSamplePoints) { await showAlert('Error', 'No sample data', 'error'); return; }
    const spacing = parseFloat(document.getElementById('cal-sample-spacing')?.value) || 30;
    const deltaZ = parseFloat(document.getElementById('cal-sample-delta-z')?.value) || 0.2;
    const mapData = {
      version: 1, grid_spacing: spacing, delta_z_mm: deltaZ,
      area_width: this.calSampleAreaW, area_height: this.calSampleAreaH,
      nx: this.calSampleNx, ny: this.calSampleNy, points: this.calSamplePoints,
      name: document.getElementById('cal-sample-name')?.value || '',
      paper: document.getElementById('cal-sample-paper')?.value || '',
      plotter: document.getElementById('cal-sample-plotter')?.value || '',
      pen: document.getElementById('cal-sample-pen')?.value || '',
    };
    try {
      const resp = await fetch('/api/surface-cal/map', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mapData),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.error);
      await this.updateHeightMapIndicator();
      showToast('Height map saved', 'success');
    } catch (e) {
      await showAlert('Error', 'Failed to save map: ' + e.message, 'error');
    }
  }

  // --- View tab: 3D surface ---

  async calViewLoad() {
    try {
      const resp = await fetch('/api/surface-cal/map');
      const data = await resp.json();
      const emptyEl = document.getElementById('cal-view-empty');
      const contentEl = document.getElementById('cal-view-content');
      if (!data.exists) {
        if (emptyEl) emptyEl.style.display = 'block';
        if (contentEl) contentEl.style.display = 'none';
        return;
      }
      if (emptyEl) emptyEl.style.display = 'none';
      if (contentEl) contentEl.style.display = 'block';

      const infoEl = document.getElementById('cal-view-info');
      if (infoEl) {
        const dz = data.delta_z_mm;
        let minL = Infinity, maxL = -Infinity;
        for (const row of data.points) for (const v of row) { if (v < minL) minL = v; if (v > maxL) maxL = v; }
        let html = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.25rem 1rem;">`;
        html += `<div><span style="color:var(--muted-foreground)">Grid:</span> ${data.nx}x${data.ny}</div>`;
        html += `<div><span style="color:var(--muted-foreground)">Spacing:</span> ${data.grid_spacing}mm</div>`;
        html += `<div><span style="color:var(--muted-foreground)">Delta Z:</span> ${dz}mm/step</div>`;
        html += `<div><span style="color:var(--muted-foreground)">Range:</span> ${(minL*dz).toFixed(2)} to ${maxL*dz >= 0 ? '+' : ''}${(maxL*dz).toFixed(2)}mm</div>`;
        html += `</div>`;
        infoEl.innerHTML = html;
      }
      this.cal3dData = data;
      this.calRender3d();
    } catch (e) { console.error('Failed to load map for 3D view:', e); }
  }

  setup3dCanvasDrag() {
    const canvas = document.getElementById('cal-3d-canvas');
    if (!canvas) return;
    let dragging = false, lastX = 0, lastY = 0;
    canvas.addEventListener('mousedown', (e) => { dragging = true; lastX = e.clientX; lastY = e.clientY; canvas.style.cursor = 'grabbing'; });
    window.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      this.cal3dRotZ += (e.clientX - lastX) * 0.008;
      this.cal3dRotX = Math.max(-Math.PI / 2, Math.min(-0.1, this.cal3dRotX + (e.clientY - lastY) * 0.008));
      lastX = e.clientX; lastY = e.clientY;
      this.calRender3d();
    });
    window.addEventListener('mouseup', () => { if (dragging) { dragging = false; canvas.style.cursor = 'grab'; } });
  }

  calRender3d() {
    const canvas = document.getElementById('cal-3d-canvas');
    if (!canvas || !this.cal3dData) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const data = this.cal3dData;
    const nx = data.nx, ny = data.ny, dz = data.delta_z_mm, srcPts = data.points;

    // Upsample grid then apply Gaussian blur for smooth "blanket" effect
    const subdiv = 5;
    const snx = (nx - 1) * subdiv + 1;
    const sny = (ny - 1) * subdiv + 1;

    // Step 1: Place source values on upsampled grid, rest = 0
    const raw = Array.from({ length: sny }, () => new Float64Array(snx));
    const weight = Array.from({ length: sny }, () => new Float64Array(snx));
    for (let iy = 0; iy < ny; iy++) {
      for (let ix = 0; ix < nx; ix++) {
        raw[iy * subdiv][ix * subdiv] = srcPts[iy][ix] * dz;
        weight[iy * subdiv][ix * subdiv] = 1;
      }
    }

    // Step 2: Gaussian spread — each source point influences neighbors like a blanket
    const sigma = subdiv * 1.2; // spread radius in subdivided cells
    const radius = Math.ceil(sigma * 2.5);
    const grid = Array.from({ length: sny }, () => new Float64Array(snx));
    const wGrid = Array.from({ length: sny }, () => new Float64Array(snx));
    for (let iy = 0; iy < ny; iy++) {
      for (let ix = 0; ix < nx; ix++) {
        const cy = iy * subdiv, cx = ix * subdiv;
        const val = srcPts[iy][ix] * dz;
        for (let dy = -radius; dy <= radius; dy++) {
          const sy = cy + dy;
          if (sy < 0 || sy >= sny) continue;
          for (let dx = -radius; dx <= radius; dx++) {
            const sx = cx + dx;
            if (sx < 0 || sx >= snx) continue;
            const w = Math.exp(-(dx * dx + dy * dy) / (2 * sigma * sigma));
            grid[sy][sx] += val * w;
            wGrid[sy][sx] += w;
          }
        }
      }
    }
    // Normalize
    for (let i = 0; i < sny; i++) {
      for (let j = 0; j < snx; j++) {
        grid[i][j] = wGrid[i][j] > 0 ? grid[i][j] / wGrid[i][j] : 0;
      }
    }

    // Find Z range from interpolated grid
    let minZ = Infinity, maxZ = -Infinity;
    for (const row of grid) for (const z of row) { if (z < minZ) minZ = z; if (z > maxZ) maxZ = z; }
    const zRange = maxZ - minZ || 0.01;

    const cosX = Math.cos(this.cal3dRotX), sinX = Math.sin(this.cal3dRotX);
    const cosZ = Math.cos(this.cal3dRotZ), sinZ = Math.sin(this.cal3dRotZ);
    const scaleXY = 0.9;
    // Proportional Z scale: map the actual mm range to a sensible visual height
    // The bed is ~800mm wide, Z variations are ~1mm, so we need amplification but not crazy
    const bedSize = Math.max(data.area_width || 800, data.area_height || 400);
    const zScale = Math.min(0.25, Math.max(0.05, (zRange / bedSize) * 80));
    const aspect = ny > 1 ? (ny - 1) / (nx - 1) : 1;

    const project = (gx, gy, gz) => {
      const x = ((gx / (snx - 1)) - 0.5) * 2 * scaleXY;
      const y = ((gy / (sny - 1)) - 0.5) * 2 * scaleXY * aspect;
      const z = ((gz - minZ) / zRange - 0.5) * 2 * zScale;
      const rx = x * cosZ - y * sinZ;
      const ry = x * sinZ + y * cosZ;
      const ry2 = ry * cosX - z * sinX;
      const rz2 = ry * sinX + z * cosX;
      const scale = Math.min(W, H) * 0.42;
      return [W / 2 + rx * scale, H / 2 - rz2 * scale + ry2 * scale * 0.15, ry * sinX + z * cosX];
    };

    // Warm color scheme: blue/white (low) → yellow → orange → red (high)
    const zColor = (z, light) => {
      const t = (z - minZ) / zRange; // 0..1
      let r, g, b;
      if (t < 0.25) {
        const s = t / 0.25;
        r = 200 + 55 * s; g = 220 + 35 * s; b = 255 - 50 * s; // cool white-blue → warm white
      } else if (t < 0.5) {
        const s = (t - 0.25) / 0.25;
        r = 255; g = 255 - 60 * s; b = 205 - 155 * s; // warm white → light orange
      } else if (t < 0.75) {
        const s = (t - 0.5) / 0.25;
        r = 255; g = 195 - 80 * s; b = 50 - 30 * s; // light orange → deep orange
      } else {
        const s = (t - 0.75) / 0.25;
        r = 255 - 40 * s; g = 115 - 75 * s; b = 20 - 10 * s; // deep orange → red
      }
      // Apply simple lighting
      const l = 0.7 + 0.3 * light;
      return `rgb(${Math.round(r * l)}, ${Math.round(g * l)}, ${Math.round(b * l)})`;
    };

    // Build quads from subdivided grid with depth sorting
    const quads = [];
    for (let i = 0; i < sny - 1; i++) {
      for (let j = 0; j < snx - 1; j++) {
        const z00 = grid[i][j], z10 = grid[i][j+1];
        const z01 = grid[i+1][j], z11 = grid[i+1][j+1];
        const avgZ = (z00 + z10 + z01 + z11) / 4;
        // Simple normal for lighting (cross product of diagonals)
        const dx = (z10 - z01), dy = (z11 - z00);
        const light = 1.0 / Math.sqrt(1 + dx * dx * 400 + dy * dy * 400);
        const cx = (j + 0.5) / (snx - 1) - 0.5, cy = (i + 0.5) / (sny - 1) - 0.5;
        const p00 = project(j, i, z00), p10 = project(j+1, i, z10);
        const p11 = project(j+1, i+1, z11), p01 = project(j, i+1, z01);
        quads.push({
          p: [p00, p10, p11, p01],
          depth: cx * sinZ + cy * cosZ,
          color: zColor(avgZ, light),
          isOrigEdge: (j % subdiv === 0 || i % subdiv === 0),
        });
      }
    }
    quads.sort((a, b) => a.depth - b.depth);

    for (const q of quads) {
      ctx.beginPath();
      ctx.moveTo(q.p[0][0], q.p[0][1]);
      for (let k = 1; k < 4; k++) ctx.lineTo(q.p[k][0], q.p[k][1]);
      ctx.closePath();
      ctx.fillStyle = q.color;
      ctx.fill();
      // Only draw wireframe on original grid lines for cleaner look
      if (q.isOrigEdge) {
        ctx.strokeStyle = 'rgba(255,255,255,0.08)';
        ctx.lineWidth = 0.5;
        ctx.stroke();
      }
    }

    // Axis labels
    ctx.font = '11px JetBrains Mono, monospace';
    ctx.fillStyle = 'rgba(255,255,255,0.5)';
    ctx.textAlign = 'left';
    const xEnd = project(snx - 1, 0, minZ);
    const yEnd = project(0, sny - 1, minZ);
    ctx.fillText(`X ${data.area_width}mm`, xEnd[0], xEnd[1] + 16);
    ctx.fillText(`Y ${data.area_height}mm`, yEnd[0] - 40, yEnd[1] + 16);

    // Color legend
    const lx = W - 25, ly = H - 120, lw = 12, lh = 100;
    for (let i = 0; i < lh; i++) {
      const z = minZ + (1 - i / lh) * zRange;
      ctx.fillStyle = zColor(z, 1.0);
      ctx.fillRect(lx, ly + i, lw, 1);
    }
    ctx.strokeStyle = 'rgba(255,255,255,0.3)';
    ctx.strokeRect(lx, ly, lw, lh);
    ctx.fillStyle = 'rgba(255,255,255,0.5)';
    ctx.font = '9px JetBrains Mono, monospace';
    ctx.textAlign = 'right';
    ctx.fillText(`${maxZ >= 0 ? '+' : ''}${maxZ.toFixed(2)}`, lx - 3, ly + 4);
    ctx.fillText(`${minZ >= 0 ? '+' : ''}${minZ.toFixed(2)}`, lx - 3, ly + lh + 1);
    ctx.textAlign = 'left';
    ctx.fillText('Drag to rotate', 10, H - 8);
  }

  async calDeleteMap() {
    const ok = await showConfirm('Delete Height Map', 'Delete the saved height map? This cannot be undone.');
    if (!ok) return;
    try {
      await fetch('/api/surface-cal/map', { method: 'DELETE' });
      await this.updateHeightMapIndicator();
      this.calViewLoad();
      showToast('Height map deleted', 'success');
    } catch (e) { await showAlert('Error', e.message, 'error'); }
  }

  async pickFolder() {
    try {
      const resp = await fetch('/api/select-output-folder', { method: 'POST' });
      const data = await resp.json();
      if (!resp.ok) return null;
      return data.output_folder;
    } catch (e) { return null; }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const app = new PlotterStudio();
  // Initialize Lucide icons after app is loaded
  if (window.lucide) {
    lucide.createIcons();
  }
});
