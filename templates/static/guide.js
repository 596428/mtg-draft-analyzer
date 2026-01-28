/**
 * MTG Draft Guide - Shared JavaScript
 */

// ==========================================
// Filter State (for Card Database page)
// ==========================================
const state = {
    grade: 'all',
    rarity: 'all',
    color: 'all',
    search: ''
};

// ==========================================
// Filter Functions
// ==========================================
function filterCards() {
    const cards = document.querySelectorAll('#all-cards-grid .card-item');
    if (!cards.length) return;

    let visibleCount = 0;

    cards.forEach(card => {
        const matchGrade = state.grade === 'all' || card.dataset.grade === state.grade;
        const matchRarity = state.rarity === 'all' || card.dataset.rarity === state.rarity;

        let matchColor = state.color === 'all';
        if (!matchColor) {
            const cardColors = card.dataset.colors || '';
            if (state.color === 'multi') {
                matchColor = cardColors.length > 1;
            } else if (state.color === 'colorless') {
                matchColor = cardColors.length === 0;
            } else {
                matchColor = cardColors.includes(state.color);
            }
        }

        const matchSearch = state.search === '' ||
            card.dataset.name.includes(state.search.toLowerCase());

        const visible = matchGrade && matchRarity && matchColor && matchSearch;
        card.classList.toggle('hidden', !visible);
        if (visible) visibleCount++;
    });

    // Show/hide no results message
    const noResults = document.getElementById('no-results');
    if (noResults) {
        noResults.classList.toggle('hidden', visibleCount > 0);
    }
}

// ==========================================
// Filter Event Listeners
// ==========================================
function setupFilterButtons(containerId, stateKey) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.querySelectorAll('button').forEach(btn => {
        btn.addEventListener('click', () => {
            // Update active state
            container.querySelectorAll('button').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Update filter state
            state[stateKey] = btn.dataset[stateKey];
            filterCards();
        });
    });
}

// ==========================================
// Archetype Tabs
// ==========================================
function setupArchetypeTabs() {
    document.querySelectorAll('.archetype-tabs button').forEach(btn => {
        btn.addEventListener('click', () => {
            const arch = btn.dataset.arch;

            // Update tab active state
            document.querySelectorAll('.archetype-tabs button').forEach(b => {
                b.classList.remove('active');
            });
            btn.classList.add('active');

            // Show corresponding panel
            document.querySelectorAll('.arch-panel').forEach(panel => {
                panel.classList.remove('active');
            });
            const panel = document.getElementById('arch-' + arch);
            if (panel) {
                panel.classList.add('active');
            }
        });
    });
}

// ==========================================
// Card Modal
// ==========================================
function showCardModal(cardEl) {
    const modal = document.getElementById('card-modal');
    if (!modal) return;

    // Handle synergy-card-text (span elements) differently
    const isSynergyText = cardEl.classList.contains('synergy-card-text');
    let imgSrc, cardName;

    if (isSynergyText) {
        imgSrc = cardEl.dataset.image || '';
        cardName = cardEl.textContent;
    } else {
        const img = cardEl.querySelector('img');
        imgSrc = img ? img.src : '';
        cardName = cardEl.querySelector('.name')?.textContent || '';
    }

    const modalImage = document.getElementById('modal-card-image');
    const modalName = document.getElementById('modal-card-name');
    const modalGrade = document.getElementById('modal-card-grade');
    const modalScore = document.getElementById('modal-card-score');
    const modalWR = document.getElementById('modal-card-wr');
    const modalRarity = document.getElementById('modal-card-rarity');
    const modalColors = document.getElementById('modal-card-colors');
    const modalViability = document.getElementById('modal-card-viability');

    if (modalImage) modalImage.src = imgSrc;
    if (modalName) modalName.textContent = cardName;
    if (modalGrade) {
        modalGrade.innerHTML =
            `<span class="grade grade-${cardEl.dataset.grade.toLowerCase().replace('+', 'plus').replace('-', 'minus')}">${cardEl.dataset.grade}</span>`;
    }
    if (modalScore) modalScore.textContent = parseFloat(cardEl.dataset.score).toFixed(1);
    if (modalWR) modalWR.textContent = (parseFloat(cardEl.dataset.wr) * 100).toFixed(1) + '%';
    if (modalRarity) {
        modalRarity.textContent = cardEl.dataset.rarity.charAt(0).toUpperCase() + cardEl.dataset.rarity.slice(1);
    }
    if (modalColors) modalColors.textContent = cardEl.dataset.colors || 'Colorless';

    // Parse archetype win rates and display detailed viability
    const archWrsRaw = cardEl.dataset.archWrs;

    let archWrs = {};
    try {
        archWrs = archWrsRaw ? JSON.parse(archWrsRaw) : {};
    } catch (e) {
        archWrs = {};
    }

    const archCount = Object.keys(archWrs).length;
    let viabilityText = '';

    if (archCount === 0) {
        // No archetype data available
        viabilityText = 'No data';
    } else if (archCount === 1) {
        // Single archetype (typically gold cards)
        const arch = Object.keys(archWrs)[0];
        const wr = (archWrs[arch] * 100).toFixed(1);
        viabilityText = arch + ' only (' + wr + '%)';
    } else {
        // Multiple archetypes - show all with win rates, sorted by WR
        const sorted = Object.entries(archWrs)
            .sort((a, b) => b[1] - a[1])
            .map(([arch, wr]) => arch + ': ' + (wr * 100).toFixed(1) + '%')
            .join(', ');
        viabilityText = sorted;
    }

    if (modalViability) modalViability.textContent = viabilityText;

    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('card-modal');
    if (modal) {
        modal.classList.remove('active');
    }
    document.body.style.overflow = '';
}

// ==========================================
// Collapsible Filter Toggle (Mobile)
// ==========================================
function setupCollapsibleFilters() {
    const filterToggle = document.querySelector('.filter-toggle');
    const filterContent = document.querySelector('.filter-content');
    if (!filterToggle || !filterContent) return;

    filterToggle.addEventListener('click', () => {
        filterToggle.classList.toggle('active');
        filterContent.classList.toggle('active');
    });
}

// ==========================================
// Smooth scroll for navigation
// ==========================================
function setupSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({
                    behavior: 'smooth'
                });
            }
        });
    });
}

// ==========================================
// Synergy card hover image setup
// ==========================================
function setupSynergyCardHover() {
    document.querySelectorAll('.synergy-card-text').forEach(el => {
        const imageUrl = el.dataset.image;
        if (imageUrl) {
            el.style.setProperty('--card-image', `url(${imageUrl})`);
        }
    });

    // Trap cards hover image
    document.querySelectorAll('.trap-card-text').forEach(el => {
        const imageUrl = el.dataset.image;
        if (imageUrl) {
            el.style.setProperty('--card-image', `url(${imageUrl})`);
        }
    });
}

// ==========================================
// Trophy Card Hover Preview
// ==========================================
function setupTrophyCardPreview() {
    // Create preview element
    const preview = document.createElement('img');
    preview.className = 'trophy-card-preview';
    preview.style.display = 'none';
    document.body.appendChild(preview);

    // Cache for loaded images to avoid flickering
    const imageCache = new Set();

    function showPreview(e) {
        const imageUrl = e.target.dataset.cardImage;
        if (!imageUrl) return;

        // Preload image if not cached
        if (!imageCache.has(imageUrl)) {
            const img = new Image();
            img.src = imageUrl;
            imageCache.add(imageUrl);
        }

        preview.src = imageUrl;
        preview.style.display = 'block';
        positionPreview(e);
    }

    function hidePreview() {
        preview.style.display = 'none';
    }

    function positionPreview(e) {
        const rect = e.target.getBoundingClientRect();
        const previewWidth = 200;
        const previewHeight = 280;

        // Position above the element, centered
        let left = rect.left + (rect.width / 2);
        let top = rect.top - 10;

        // Adjust if too close to viewport edges
        if (left - previewWidth / 2 < 10) {
            left = previewWidth / 2 + 10;
        }
        if (left + previewWidth / 2 > window.innerWidth - 10) {
            left = window.innerWidth - previewWidth / 2 - 10;
        }
        if (top - previewHeight < 10) {
            // Show below instead
            top = rect.bottom + previewHeight + 10;
            preview.style.transform = 'translate(-50%, 0)';
        } else {
            preview.style.transform = 'translate(-50%, -100%)';
        }

        preview.style.left = left + 'px';
        preview.style.top = top + 'px';
    }

    // Attach event listeners to trophy card hover elements
    document.querySelectorAll('.trophy-card-hover').forEach(el => {
        el.addEventListener('mouseenter', showPreview);
        el.addEventListener('mouseleave', hidePreview);
        el.addEventListener('mousemove', positionPreview);
    });
}

// ==========================================
// Initialize all functionality
// ==========================================
function initializeDraftGuide() {
    // Filter setup (only on cards page)
    setupFilterButtons('grade-filters', 'grade');
    setupFilterButtons('rarity-filters', 'rarity');
    setupFilterButtons('color-filters', 'color');

    // Search setup
    const searchInput = document.getElementById('card-search');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            state.search = e.target.value;
            filterCards();
        });
    }

    // Archetype tabs
    setupArchetypeTabs();

    // Collapsible filters (mobile)
    setupCollapsibleFilters();

    // Smooth scroll
    setupSmoothScroll();

    // Synergy card hover
    setupSynergyCardHover();

    // Trophy card preview
    setupTrophyCardPreview();

    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });
}

// Run initialization when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeDraftGuide);
} else {
    initializeDraftGuide();
}
