document.addEventListener("DOMContentLoaded", () => {
    const bars = document.querySelectorAll(".progress-fill");

    bars.forEach((bar) => {
        const percent = Number(bar.dataset.percent || 0);
        bar.style.width = `${Math.min(percent, 100)}%`;
    });
});