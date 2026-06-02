/* SIDEBAR FUNCTIONS */
function openMenu() {
    document.getElementById('sidebar').classList.add('active');
    document.getElementById('sidebar-overlay').classList.add('active');
}

function closeMenu() {
    document.getElementById('sidebar').classList.remove('active');
    document.getElementById('sidebar-overlay').classList.remove('active');
}

/* PARTICLE SYSTEM */
(function() {
    const canvas = document.getElementById('particles-canvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    let W, H, particles = [];

    function resize() {
        W = canvas.width = window.innerWidth;
        H = canvas.height = window.innerHeight;
    }

    function createParticles(n) {
        particles = [];
        for (let i = 0; i < n; i++) {
            particles.push({
                x: Math.random() * W,
                y: Math.random() * H,
                r: Math.random() * 1.2 + 0.3,
                vx: (Math.random() - 0.5) * 0.2,
                vy: (Math.random() - 0.5) * 0.2,
                alpha: Math.random() * 0.4 + 0.1
            });
        }
    }

    function draw() {
        ctx.clearRect(0, 0, W, H);
        particles.forEach(p => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(148, 163, 184, ${p.alpha})`;
            ctx.fill();

            p.x += p.vx;
            p.y += p.vy;

            if (p.x < 0) p.x = W;
            if (p.x > W) p.x = 0;
            if (p.y < 0) p.y = H;
            if (p.y > H) p.y = 0;
        });
        requestAnimationFrame(draw);
    }

    resize();
    createParticles(90);
    draw();
    window.addEventListener('resize', () => { resize(); createParticles(90); });
})();

/* COUNTER ANIMATION */
function animateCounter(el) {
    const target = parseInt(el.getAttribute('data-count'));
    let current = 0;
    const duration = 2000;
    const step = target / (duration / 16);
    
    const update = () => {
        current += step;
        if (current < target) {
            el.innerText = Math.floor(current).toLocaleString() + (el.innerText.includes('+') ? '+' : '');
            requestAnimationFrame(update);
        } else {
            el.innerText = target.toLocaleString() + (el.innerText.includes('+') ? '+' : '');
        }
    };
    update();
}

/* INTERSECTION OBSERVER FOR COUNTERS */
document.addEventListener('DOMContentLoaded', () => {
    const observer = new IntersectionObserver(entries => {
        entries.forEach(e => {
            if (e.isIntersecting) {
                const counters = e.target.querySelectorAll('[data-count]');
                counters.forEach(animateCounter);
                observer.unobserve(e.target);
            }
        });
    }, { threshold: 0.3 });

    const heroRight = document.querySelector('.hero-right');
    if (heroRight) observer.observe(heroRight);
});
