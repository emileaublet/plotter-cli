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
    if (window.lucide) lucide.createIcons();
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

class PlotterStudio {
  constructor() {
    this.canvas = document.getElementById('canvas');
    this.ctx = this.canvas.getContext('2d');
    this.container = document.getElementById('canvas-container');

    this.papers = [];
    this.svgLibrary = [];
    this.selectedPaperId = null;
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

    this.init();
  }

  async init() {
    await this.loadSettings();
    this.setupCanvas();
    this.setupEventListeners();
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
      document.getElementById('settings-z-up-long').value = this.settings.z_up_long;
      document.getElementById('settings-z-up-short').value = this.settings.z_up_short;
      document.getElementById('settings-z-up-threshold').value = this.settings.z_up_threshold;
      document.getElementById('settings-z-down').value = this.settings.z_down;
      document.getElementById('settings-feed-rate-draw').value = this.settings.feed_rate_draw;
      document.getElementById('settings-feed-rate-travel').value = this.settings.feed_rate_travel;
      document.getElementById('settings-feed-rate-z').value = this.settings.feed_rate_z;
      document.getElementById('settings-registration-marks-length').value = this.settings.registration_marks_length;
    }

    modal.classList.add('active');
    lucide.createIcons();
  }

  async saveSettings() {
    try {
      const settingsData = {
        area_width: parseFloat(document.getElementById('settings-area-width').value),
        area_height: parseFloat(document.getElementById('settings-area-height').value),
        z_up_long: parseFloat(document.getElementById('settings-z-up-long').value),
        z_up_short: parseFloat(document.getElementById('settings-z-up-short').value),
        z_up_threshold: parseFloat(document.getElementById('settings-z-up-threshold').value),
        z_down: parseFloat(document.getElementById('settings-z-down').value),
        feed_rate_draw: parseInt(document.getElementById('settings-feed-rate-draw').value),
        feed_rate_travel: parseInt(document.getElementById('settings-feed-rate-travel').value),
        feed_rate_z: parseInt(document.getElementById('settings-feed-rate-z').value),
        registration_marks_length: parseFloat(document.getElementById('settings-registration-marks-length').value),
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
      paperModal?.classList.add('active');
    });

    closeModalBtn?.addEventListener('click', () => {
      this.closePaperModal();
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

    // Toolbar tools
    document.getElementById('tool-select')?.addEventListener('click', () => this.setTool('select'));
    document.getElementById('tool-pan')?.addEventListener('click', () => this.setTool('pan'));

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
    this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
    this.canvas.addEventListener('mouseup', () => this.onMouseUp());
    this.canvas.addEventListener('wheel', (e) => this.onWheel(e), { passive: false });

    // Mouse position tracking
    this.canvas.addEventListener('mousemove', (e) => {
      const point = this.getCanvasPoint(e);
      const mouseLabel = document.getElementById('mouse-position');
      if (mouseLabel) {
        mouseLabel.textContent = `${point.x.toFixed(1)}mm, ${point.y.toFixed(1)}mm`;
      }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
      if (e.key === 'v' || e.key === 'V') this.setTool('select');
      if (e.key === 'h' || e.key === 'H') this.setTool('pan');
      if (e.key === 'Escape' || e.key === 'Esc') {
        // If pan tool is active, switch back to select
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
    });

    document.addEventListener('keyup', (e) => {
      if (e.key === ' ') {
        this.panning = false;
        this.canvas.style.cursor = this.activeTool === 'pan' ? 'grab' : 'crosshair';
      }
    });
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
    if (window.lucide) lucide.createIcons();
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
      // Reinitialize icons after DOM update
      if (window.lucide) lucide.createIcons();
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
    
    // Reinitialize icons after DOM update
    if (window.lucide) lucide.createIcons();
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
      // Reinitialize icons after DOM update
      if (window.lucide) lucide.createIcons();
      return;
    }

    list.innerHTML = this.papers
      .map((paper) => {
        const name = paper.paper_name || 'Custom';
        const size = `${paper.paper_width.toFixed(0)}mm × ${paper.paper_height.toFixed(0)}mm`;
        const assigned = paper.svg_id ? `Assigned: ${this.getSvgFilename(paper.svg_id)}` : 'No SVG';
        const isSelected = paper.id === this.selectedPaperId;
        return `
          <div class="list-item ${isSelected ? 'selected' : ''}" data-paper-id="${paper.id}">
            <div class="list-item-content">
              <div class="list-item-name">${this.escapeHtml(name)}</div>
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
    
    // Reinitialize icons after DOM update
    if (window.lucide) lucide.createIcons();
  }

  getSvgFilename(svgId) {
    const svg = this.svgLibrary.find((s) => s.id === svgId);
    return svg ? svg.filename : 'Unknown SVG';
  }

  selectPaper(paperId) {
    this.selectedPaperId = paperId;
    this.updatePaperList();
    this.updateInspector();
    this.render();
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
      this.updatePaperList();
      this.updateInspector();
      this.render();
    } catch (error) {
      console.error('Error removing paper:', error);
      await showAlert('Error', 'Failed to remove paper: ' + error.message, 'error');
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
      confirmMessage += `\n\nThis SVG is assigned to ${assignedCount} paper${assignedCount > 1 ? 's' : ''}. Deleting it will also remove ${assignedCount > 1 ? 'those papers' : 'that paper'} from the canvas.`;
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
      const removedPaperIds = result.paper_ids || [];

      // Remove SVG from library
      this.svgLibrary = this.svgLibrary.filter((s) => s.id !== svgId);

      // Remove papers that were deleted
      if (removedPaperIds.length > 0) {
        this.papers = this.papers.filter((p) => !removedPaperIds.includes(p.id));
        // Clear selection if selected paper was removed
        if (removedPaperIds.includes(this.selectedPaperId)) {
          this.selectedPaperId = null;
        }
      }

      // Update UI
      this.updateSvgLibraryList();
      this.updatePaperList();
      this.updateInspector();
      this.render();
    } catch (error) {
      console.error('Error removing SVG:', error);
      await showAlert('Error', 'Failed to remove SVG: ' + error.message, 'error');
    }
  }

  updateInspector() {
    const content = document.getElementById('inspector-content');
    if (!content) return;

    if (!this.selectedPaperId) {
      content.innerHTML = `
        <div class="empty-state">
          ${lucideIconHTML('sliders', 32, '', 'opacity: 0.3;')}
          <p>No paper selected</p>
          <p class="empty-state-hint">Select a paper to edit</p>
        </div>
      `;
      // Reinitialize icons after DOM update
      if (window.lucide) lucide.createIcons();
      return;
    }

    const paper = this.papers.find((p) => p.id === this.selectedPaperId);
    if (!paper) return;

    const assignedSvg = paper.svg_id ? this.svgLibrary.find((s) => s.id === paper.svg_id) : null;

    content.innerHTML = `
      <div class="form-group">
        <label>Paper Size</label>
        <div class="info-value" style="margin-top: 0.25rem">
          ${paper.paper_name || 'Custom'} (${paper.paper_width.toFixed(0)} × ${paper.paper_height.toFixed(0)}mm)
        </div>
      </div>

      <div class="form-group">
        <label>Assign SVG</label>
        <select id="inspector-assign-svg" class="input-select" style="margin-top: 0.5rem">
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
            <input type="number" id="inspector-x" class="input-number" value="${paper.x ?? 0}" step="0.1" />
            <span class="input-unit">mm</span>
          </div>
          <div class="input-group">
            <input type="number" id="inspector-y" class="input-number" value="${paper.y ?? 0}" step="0.1" />
            <span class="input-unit">mm</span>
          </div>
        </div>
        <div class="transform-grid" style="margin-top: 0.75rem">
          <div class="input-group">
            <input type="number" id="inspector-rotation" class="input-number" value="${paper.rotation ?? 0}" step="90" />
            <span class="input-unit">°</span>
          </div>
          <div style="display: flex; gap: 0.5rem">
            <button class="btn btn-secondary" id="rotate-left-btn" style="flex: 1">↺ Left</button>
            <button class="btn btn-secondary" id="rotate-right-btn" style="flex: 1">↻ Right</button>
          </div>
        </div>
      </div>

      <div class="form-actions">
        <button class="btn btn-secondary btn-full" id="clone-paper-btn">Clone Paper</button>
        <button class="btn btn-danger btn-full" id="remove-paper-inspector-btn">Remove Paper</button>
      </div>
    `;

    // Event listeners for inspector controls
    const assignSelect = document.getElementById('inspector-assign-svg');
    assignSelect?.addEventListener('change', (e) => {
      this.assignSvgToPaper(e.target.value || null);
    });

    const xInput = document.getElementById('inspector-x');
    const yInput = document.getElementById('inspector-y');
    const rotationInput = document.getElementById('inspector-rotation');

    xInput?.addEventListener('input', (e) => {
      this.updatePaperPosition('x', e.target.value);
    });

    yInput?.addEventListener('input', (e) => {
      this.updatePaperPosition('y', e.target.value);
    });

    rotationInput?.addEventListener('input', (e) => {
      this.updatePaperRotation(Number(e.target.value));
    });

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
    
    // Reinitialize icons after DOM update
    if (window.lucide) lucide.createIcons();
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
      this.updateInspector();
      this.render();
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
      this.updatePaperList();
      this.render();

      // Close modal and reset form
      this.closePaperModal();
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

  async updatePaperPosition(axis, value) {
    if (!this.selectedPaperId) return;

    const paper = this.papers.find((p) => p.id === this.selectedPaperId);
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
      this.updatePaperList();
      this.render();
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

      this.updatePaperList();
      this.updateInspector();
      this.render();
    } catch (error) {
      console.error('Auto-arrange error:', error);
      await showAlert('Error', 'Auto-arrange failed: ' + error.message, 'error');
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
      this.selectPaper(hitPaper.id);
      this.dragging = true;
      this.dragStart = point;
      this.dragStartTransform = { x: hitPaper.x || 0, y: hitPaper.y || 0 };
      event.preventDefault();
    } else {
      this.selectedPaperId = null;
      this.updatePaperList();
      this.updateInspector();
      this.render();
    }
  }

  onMouseMove(event) {
    if (this.panning) {
      const dx = event.clientX - this.dragStart.x;
      const dy = event.clientY - this.dragStart.y;
      this.canvasTransform.x = this.dragStartTransform.x + dx;
      this.canvasTransform.y = this.dragStartTransform.y + dy;
      this.render();
      return;
    }

    if (!this.dragging || !this.selectedPaperId) return;

    const point = this.getCanvasPoint(event);
    const paper = this.papers.find((p) => p.id === this.selectedPaperId);
    if (!paper) return;

    const dx = point.x - this.dragStart.x;
    const dy = point.y - this.dragStart.y;

    paper.x = this.dragStartTransform.x + dx;
    paper.y = this.dragStartTransform.y + dy;

    // Update inspector inputs
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
      const paper = this.papers.find((p) => p.id === this.selectedPaperId);
      if (paper) {
        await this.updatePaperPosition('x', paper.x);
        await this.updatePaperPosition('y', paper.y);
      }
    }

    this.dragging = false;
    this.dragStartTransform = null;
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
    this.ctx.strokeStyle = '#e0e0e0';
    this.ctx.lineWidth = 1;

    const gridSizePx = 10 * this.scale;
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

    // Selection highlight
    if (paper.id === this.selectedPaperId) {
      this.ctx.strokeStyle = '#00E5FF';
      this.ctx.lineWidth = 3 / this.scale;
      this.ctx.setLineDash([5 / this.scale, 5 / this.scale]);
      this.ctx.strokeRect(-width / 2, -height / 2, width, height);
      this.ctx.setLineDash([]);
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
      await showAlert('Export Successful', `Files saved to:\n${result.output_folder}`, 'success');
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

      // Update UI
      this.updatePaperList();
      this.updateSvgLibraryList();
      this.updateInspector();
      this.render();

      await showAlert('Cleared', `Removed ${result.papers_removed} paper${result.papers_removed !== 1 ? 's' : ''} and ${result.svgs_removed} SVG${result.svgs_removed !== 1 ? 's' : ''}.`, 'success');
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
}

document.addEventListener('DOMContentLoaded', () => {
  new PlotterStudio();
  // Initialize Lucide icons after app is loaded
  if (window.lucide) {
    lucide.createIcons();
  }
});
