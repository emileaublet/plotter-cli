// Plotter Studio - Main Application JavaScript

class PlotterStudio {
    constructor() {
        this.canvas = document.getElementById('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.overlay = document.getElementById('canvas-overlay');

        this.papers = [];
        this.svgLibrary = [];
        this.selectedPaperId = null;
        this.settings = null;

        this.scale = 2; // pixels per mm
        this.canvasWidth = 880; // mm
        this.canvasHeight = 470; // mm

        this.dragging = false;
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
    }

    async loadSettings() {
        try {
            const response = await fetch('/api/settings');
            this.settings = await response.json();
            this.canvasWidth = this.settings.area_width;
            this.canvasHeight = this.settings.area_height;
            this.setupCanvas();
            this.populatePaperSelects();
        } catch (error) {
            console.error('Failed to load settings:', error);
        }
    }

    setupCanvas() {
        const pixelWidth = this.canvasWidth * this.scale;
        const pixelHeight = this.canvasHeight * this.scale;

        this.canvas.width = pixelWidth;
        this.canvas.height = pixelHeight;
        this.canvas.style.width = `${pixelWidth}px`;
        this.canvas.style.height = `${pixelHeight}px`;

        const sizeLabel = document.getElementById('canvas-size');
        if (sizeLabel) {
            sizeLabel.textContent = `Canvas: ${this.canvasWidth}mm × ${this.canvasHeight}mm`;
        }
    }

    setupEventListeners() {
        const fileInput = document.getElementById('file-input');
        const addSvgBtn = document.getElementById('add-svg-btn');
        addSvgBtn?.addEventListener('click', () => fileInput?.click());
        fileInput?.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.addSvg(e.target.files[0]);
            }
        });

        document.getElementById('export-btn')?.addEventListener('click', () => this.export());
        document.getElementById('add-paper-btn')?.addEventListener('click', () => this.addPaperFromSelect());

        document.getElementById('transform-x')?.addEventListener('input', (e) => {
            this.updatePaperPosition('x', e.target.value);
        });
        document.getElementById('transform-y')?.addEventListener('input', (e) => {
            this.updatePaperPosition('y', e.target.value);
        });

        document.getElementById('paper-size-select')?.addEventListener('change', (e) => {
            this.updatePaperSize(e.target.value);
        });
        document.getElementById('assign-svg-select')?.addEventListener('change', (e) => {
            this.assignSvgToPaper(e.target.value || null);
        });

        document.getElementById('clone-paper-btn')?.addEventListener('click', () => this.cloneSelectedPaper());
        document.getElementById('remove-paper-btn')?.addEventListener('click', () => this.removeSelectedPaper());
        document.getElementById('auto-arrange-btn')?.addEventListener('click', () => this.autoArrange());

        this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
        this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
        this.canvas.addEventListener('mouseup', () => this.onMouseUp());

        this.canvas.addEventListener('mousemove', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const x = (e.clientX - rect.left) / this.scale;
            const y = (e.clientY - rect.top) / this.scale;
            const mouseLabel = document.getElementById('mouse-position');
            if (mouseLabel) {
                mouseLabel.textContent = `Mouse: ${x.toFixed(1)}mm, ${y.toFixed(1)}mm`;
            }
        });
    }

    populatePaperSelects() {
        if (!this.settings || !this.settings.papers) return;

        const addPaperSelect = document.getElementById('add-paper-select');
        const paperSizeSelect = document.getElementById('paper-size-select');

        const buildOptions = (selectEl, includePlaceholder = false) => {
            if (!selectEl) return;
            const current = selectEl.value;
            selectEl.innerHTML = '';

            if (includePlaceholder) {
                const placeholder = document.createElement('option');
                placeholder.value = '';
                placeholder.textContent = 'Select paper size...';
                selectEl.appendChild(placeholder);
            } else {
                const custom = document.createElement('option');
                custom.value = 'custom';
                custom.textContent = 'Custom (SVG size)';
                selectEl.appendChild(custom);
            }

            for (const paper of this.settings.papers) {
                const landscape = document.createElement('option');
                landscape.value = `${paper.name}_landscape`;
                landscape.textContent = `${paper.name} (Landscape) - ${paper.width.toFixed(0)}×${paper.height.toFixed(0)}mm`;
                selectEl.appendChild(landscape);

                const portrait = document.createElement('option');
                portrait.value = `${paper.name}_portrait`;
                portrait.textContent = `${paper.name} (Portrait) - ${paper.height.toFixed(0)}×${paper.width.toFixed(0)}mm`;
                selectEl.appendChild(portrait);
            }

            if (current && Array.from(selectEl.options).some((o) => o.value === current)) {
                selectEl.value = current;
            }
        };

        buildOptions(addPaperSelect, true);
        buildOptions(paperSizeSelect, false);
    }

    async loadSvgLibrary() {
        try {
            const response = await fetch('/api/list-svgs');
            const svgs = await response.json();

            const loaded = await Promise.all(svgs.map((svg) => this.prepareSvgLibraryEntry(svg)));
            this.svgLibrary = loaded.filter(Boolean);

            this.updateSvgLibraryList();
            this.populateAssignSelect();
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
            list.innerHTML = '<p class="empty-state">No SVGs in library</p>';
            return;
        }

        list.innerHTML = this.svgLibrary
            .map(
                (svg) => `
                <div class="svg-item" data-svg-id="${svg.id}">
                    <div class="svg-item-name">${svg.filename}</div>
                    <div class="svg-item-info">${svg.width.toFixed(1)}mm × ${svg.height.toFixed(1)}mm</div>
                </div>
            `,
            )
            .join('');
    }

    populateAssignSelect() {
        const select = document.getElementById('assign-svg-select');
        if (!select) return;

        const current = select.value;
        select.innerHTML = '';

        const noneOption = document.createElement('option');
        noneOption.value = '';
        noneOption.textContent = 'None';
        select.appendChild(noneOption);

        for (const svg of this.svgLibrary) {
            const option = document.createElement('option');
            option.value = svg.id;
            option.textContent = `${svg.filename} (${svg.width.toFixed(0)}×${svg.height.toFixed(0)}mm)`;
            select.appendChild(option);
        }

        if (current && Array.from(select.options).some((o) => o.value === current)) {
            select.value = current;
        }
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
            list.innerHTML = '<p class="empty-state">No papers added yet</p>';
            return;
        }

        list.innerHTML = this.papers
            .map((paper) => {
                const name = paper.paper_name || 'Custom';
                const size = `${paper.paper_width.toFixed(0)}mm × ${paper.paper_height.toFixed(0)}mm`;
                const assigned = paper.svg_id ? `Assigned: ${this.getSvgFilename(paper.svg_id)}` : 'No SVG assigned';
                return `
                    <div class="svg-item ${paper.id === this.selectedPaperId ? 'selected' : ''}" data-paper-id="${paper.id}">
                        <div class="svg-item-name">${name}</div>
                        <div class="svg-item-info">${size}</div>
                        <div class="svg-item-info">${assigned}</div>
                    </div>
                `;
            })
            .join('');

        list.querySelectorAll('.svg-item').forEach((item) => {
            item.addEventListener('click', () => {
                const paperId = item.dataset.paperId;
                this.selectPaper(paperId);
            });
        });
    }

    getSvgFilename(svgId) {
        const svg = this.svgLibrary.find((s) => s.id === svgId);
        return svg ? svg.filename : 'Unknown SVG';
    }

    selectPaper(paperId) {
        this.selectedPaperId = paperId;
        this.updatePaperList();
        this.updateTransformPanel();
        this.render();
    }

    updateTransformPanel() {
        const panel = document.getElementById('transform-panel');
        if (!panel) return;

        if (!this.selectedPaperId) {
            panel.style.display = 'none';
            return;
        }

        panel.style.display = 'block';
        const paper = this.papers.find((p) => p.id === this.selectedPaperId);
        if (!paper) return;

        document.getElementById('transform-x').value = paper.x ?? 0;
        document.getElementById('transform-y').value = paper.y ?? 0;
        console.debug('[PlotterStudio] updateTransformPanel set inputs', {
            id: paper.id,
            x: paper.x,
            y: paper.y,
        });

        const paperSizeSelect = document.getElementById('paper-size-select');
        if (paperSizeSelect) {
            if (paper.paper_name) {
                const orientation = paper.paper_width >= paper.paper_height ? 'landscape' : 'portrait';
                paperSizeSelect.value = `${paper.paper_name}_${orientation}`;
            } else {
                paperSizeSelect.value = 'custom';
            }
        }

        const assignSelect = document.getElementById('assign-svg-select');
        if (assignSelect) {
            assignSelect.value = paper.svg_id || '';
        }
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
            this.populateAssignSelect();
            this.updateTransformPanel();
            this.render();
        } catch (error) {
            console.error('Error adding SVG:', error);
            alert('Failed to add SVG: ' + error.message);
        }
    }

    async addPaperFromSelect() {
        const select = document.getElementById('add-paper-select');
        if (!select || !select.value) {
            alert('Please select a paper size first.');
            return;
        }

        const [paperName, orientation] = select.value.split('_');

        try {
            const response = await fetch('/api/add-paper', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ paper_name: paperName, orientation }),
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
        } catch (error) {
            console.error('Error adding paper:', error);
            alert('Failed to add paper: ' + error.message);
        }
    }

    async updatePaperPosition(axis, value) {
        if (!this.selectedPaperId) return;

        const paper = this.papers.find((p) => p.id === this.selectedPaperId);
        if (!paper) return;

        if (value === '' || value === null || value === undefined) {
            console.debug('[PlotterStudio] Ignored empty input', { axis, value });
            return;
        }

        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            console.debug('[PlotterStudio] Ignored non-numeric input', { axis, value });
            return;
        }

        console.debug('[PlotterStudio] updatePaperPosition', {
            id: paper.id,
            axis,
            value: numericValue,
            before: { x: paper.x, y: paper.y },
        });

        paper[axis] = numericValue;
        this.render();

        try {
            const payload = {
                id: paper.id,
                x: Number.isFinite(paper.x) ? paper.x : 0,
                y: Number.isFinite(paper.y) ? paper.y : 0,
            };

            const response = await fetch('/api/update-paper', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (response.ok) {
                const result = await response.json();
                Object.assign(paper, result.paper);
                console.debug('[PlotterStudio] updatePaperPosition response', result.paper);
                this.updateTransformPanel();
            }
        } catch (error) {
            console.error('Error updating paper position:', error);
        }
    }

    async updatePaperSize(value) {
        if (!this.selectedPaperId) return;

        const paper = this.papers.find((p) => p.id === this.selectedPaperId);
        if (!paper || !this.settings) return;

        if (value === 'custom') {
            paper.paper_name = null;
            paper.paper_width = paper.paper_width || paper.paper_height || 100;
            paper.paper_height = paper.paper_height || paper.paper_width || 100;
        } else {
            const [paperName, orientation] = value.split('_');
            const config = this.settings.papers.find((p) => p.name === paperName);
            if (!config) return;

            paper.paper_name = paperName;
            if (orientation === 'landscape') {
                paper.paper_width = config.width;
                paper.paper_height = config.height;
            } else {
                paper.paper_width = config.height;
                paper.paper_height = config.width;
            }
        }

        this.render();

        try {
            const response = await fetch('/api/update-paper', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: paper.id,
                    paper_name: paper.paper_name,
                    paper_width: paper.paper_width,
                    paper_height: paper.paper_height,
                }),
            });

            if (response.ok) {
                const result = await response.json();
                Object.assign(paper, result.paper);
                this.updateTransformPanel();
            }
        } catch (error) {
            console.error('Error updating paper size:', error);
        }
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
                this.updateTransformPanel();
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
            alert('Failed to clone paper: ' + error.message);
        }
    }

    async removeSelectedPaper() {
        if (!this.selectedPaperId) return;

        try {
            const response = await fetch(`/api/remove-paper/${this.selectedPaperId}`, { method: 'DELETE' });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to remove paper');
            }

            this.papers = this.papers.filter((p) => p.id !== this.selectedPaperId);
            this.selectedPaperId = null;
            this.updatePaperList();
            this.updateTransformPanel();
            this.render();
        } catch (error) {
            console.error('Error removing paper:', error);
            alert('Failed to remove paper: ' + error.message);
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

            this.updateTransformPanel();
            this.render();
        } catch (error) {
            console.error('Auto-arrange error:', error);
            alert('Auto-arrange failed: ' + error.message);
        }
    }

    getCanvasPoint(event) {
        const rect = this.canvas.getBoundingClientRect();
        return { x: (event.clientX - rect.left) / this.scale, y: (event.clientY - rect.top) / this.scale };
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
            this.updateTransformPanel();
            this.render();
        }
    }

    onMouseMove(event) {
        if (!this.dragging || !this.selectedPaperId) return;

        const point = this.getCanvasPoint(event);
        const paper = this.papers.find((p) => p.id === this.selectedPaperId);
        if (!paper) return;

        const dx = point.x - this.dragStart.x;
        const dy = point.y - this.dragStart.y;

        paper.x = this.dragStartTransform.x + dx;
        paper.y = this.dragStartTransform.y + dy;

        this.updateTransformInputs();
        this.render();
    }

    async onMouseUp() {
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

    updateTransformInputs() {
        if (!this.selectedPaperId) return;
        const paper = this.papers.find((p) => p.id === this.selectedPaperId);
        if (!paper) return;

        const xInput = document.getElementById('transform-x');
        const yInput = document.getElementById('transform-y');
        if (xInput) xInput.value = paper.x ?? 0;
        if (yInput) yInput.value = paper.y ?? 0;
        console.debug('[PlotterStudio] updateTransformInputs set inputs', {
            id: paper.id,
            x: paper.x,
            y: paper.y,
        });
    }

    render() {
        this.ctx.fillStyle = '#ffffff';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        this.drawGrid();
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

        this.ctx.strokeStyle = '#ffaa00';
        this.ctx.lineWidth = 2 / this.scale;
        this.ctx.setLineDash([10 / this.scale, 5 / this.scale]);
        this.ctx.strokeRect(x, y, width, height);
        this.ctx.setLineDash([]);

        if (paper.id === this.selectedPaperId) {
            this.ctx.strokeStyle = '#4a9eff';
            this.ctx.lineWidth = 2 / this.scale;
            this.ctx.setLineDash([5 / this.scale, 5 / this.scale]);
            this.ctx.strokeRect(x, y, width, height);
            this.ctx.setLineDash([]);
        }

        if (paper.svg_id) {
            const svg = this.svgLibrary.find((s) => s.id === paper.svg_id);
            if (svg && svg.previewImage) {
                const scale = paper.svg_scale || 1.0;
                const scaledWidth = svg.width * scale * this.scale;
                const scaledHeight = svg.height * scale * this.scale;
                const svgX = x + (width - scaledWidth) / 2;
                const svgY = y + (height - scaledHeight) / 2;

                this.ctx.drawImage(svg.previewImage, svgX, svgY, scaledWidth, scaledHeight);
            }
        }
    }

    async export() {
        if (this.papers.length === 0) {
            alert('No papers to export');
            return;
        }

        const outputFolder = prompt('Enter output folder path (or leave empty for temp folder):');

        try {
            const response = await fetch('/api/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ output_folder: outputFolder || null }),
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Export failed');
            }

            const result = await response.json();
            alert(`Export successful!\n\nFiles saved to:\n${result.output_folder}`);
        } catch (error) {
            console.error('Export error:', error);
            alert('Export failed: ' + error.message);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new PlotterStudio();
});

