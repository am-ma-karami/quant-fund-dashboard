async function fetchJSON(url) {
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(
            `${url} failed: ${response.status}`
        );
    }

    return response.json();
}


async function loadTopFunds() {
    const container =
        document.getElementById("top-funds");

    try {
        container.innerHTML =
            `<div class="loading">در حال دریافت اطلاعات...</div>`;

        const data = await fetchJSON(
            "/api/dashboard/top-funds"
        );

        if (!data.length) {
            container.innerHTML =
                `<div class="empty-state">
                    داده‌ای موجود نیست.
                 </div>`;
            return;
        }

        container.innerHTML = data.map(fund => `
            <a
                href="/fund/${fund.reg_no}"
                class="fund-row"
            >
                <span>${fund.rank}</span>
                <span>${fund.name}</span>
                <strong>
                    ${Number(fund.return_30d).toFixed(2)}%
                </strong>
            </a>
        `).join("");

    } catch (error) {
        console.error(
            "Top funds loading failed:",
            error
        );

        container.innerHTML =
            `<div class="error-state">
                دریافت اطلاعات Top 10 ناموفق بود.
             </div>`;
    }
}


async function loadHeatmap() {
    const container =
        document.getElementById("heatmap-container");

    try {
        container.innerHTML =
            `<div class="loading">در حال دریافت اطلاعات...</div>`;

        const data = await fetchJSON(
            "/api/dashboard/heatmap"
        );

        if (!data.length) {
            container.innerHTML =
                `<div class="empty-state">
                    داده‌ای برای Heatmap موجود نیست.
                 </div>`;
            return;
        }

        renderHeatmap(data);

    } catch (error) {
        console.error(
            "Heatmap loading failed:",
            error
        );

        container.innerHTML =
            `<div class="error-state">
                دریافت اطلاعات Heatmap ناموفق بود.
             </div>`;
    }
}


async function loadMarketPulse() {
    try {
        const data = await fetchJSON("/api/market-pulse");
        
        document.getElementById('pulse_total').innerText = data.total;
        document.getElementById('pulse_positive').innerText = data.positive + ' ↑';
        document.getElementById('pulse_negative').innerText = data.negative + ' ↓';
        document.getElementById('pulse_unchanged').innerText = data.unchanged;
        
        document.getElementById('breadth_text').innerText = data.breadth + '%';
        document.getElementById('breadth_bar').style.width = data.breadth + '%';
        
        document.getElementById('vol_text').innerText = data.up_volume_ratio + '%';
        document.getElementById('vol_bar').style.width = data.up_volume_ratio + '%';
        document.getElementById('total_trades_txt').innerText = 'Trades: ' + data.total_trades.toLocaleString();
        
    } catch (error) {
        console.error("Market pulse loading failed:", error);
    }
}


document.addEventListener(
    "DOMContentLoaded",
    () => {
        loadTopFunds();
        loadHeatmap();
        loadMarketPulse();
        
        setInterval(loadMarketPulse, 60000);
    }
);