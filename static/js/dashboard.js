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
    const container = document.getElementById("top-funds");
    const canvas = document.getElementById("bigPictureChart");

    if (!container || !canvas) {
        return;
    }

    try {
        container.innerHTML =
            `<div class="loading text-center p-3">در حال دریافت اطلاعات...</div>`;

        const data = await fetchJSON("/api/dashboard/top-funds");

        if (!data.length) {
            container.innerHTML =
                `<div class="empty-state text-center p-3 text-muted">داده‌ای موجود نیست.</div>`;
            return;
        }

        container.style.display = "none";
        canvas.style.display = "block";

        const labels = data.map(item => item.name);
        const values = data.map(item => Number(item.return_30d || 0));

        if (window.topFundsChart) {
            window.topFundsChart.destroy();
        }

        window.topFundsChart = new Chart(canvas, {
            type: "bar",
            data: {
                labels,
                datasets: [{
                    label: "بازدهی ۳۰ روزه (%)",
                    data: values,
                    backgroundColor: "rgba(54, 162, 235, 0.7)",
                    borderColor: "rgba(54, 162, 235, 1)",
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: { beginAtZero: false }
                }
            }
        });

    } catch (error) {
        console.error("Top funds loading failed:", error);
        container.style.display = "block";
        container.innerHTML =
            `<div class="error-state text-center p-3 text-danger">دریافت اطلاعات Top 10 ناموفق بود.</div>`;
        canvas.style.display = "none";
    }
}


async function loadHeatmap() {
    const container = document.getElementById("heatmap-container");

    if (!container) {
        return;
    }

    try {
        container.innerHTML =
            `<div class="loading text-center p-5">در حال دریافت اطلاعات...</div>`;

        const data = await fetchJSON("/api/dashboard/heatmap");

        if (!data.length) {
            container.innerHTML =
                `<div class="empty-state text-center p-5 text-muted">داده‌ای برای Heatmap موجود نیست.</div>`;
            return;
        }

        if (window.heatmapChart) {
            window.heatmapChart.destroy();
        }

        window.heatmapChart = Highcharts.chart(container, {
            colorAxis: {
                min: -15,
                max: 15,
                stops: [
                    [0, "#dc3545"],
                    [0.5, "#f8f9fa"],
                    [1, "#198754"]
                ]
            },
            series: [{
                type: "treemap",
                layoutAlgorithm: "squarified",
                data: data,
                dataLabels: {
                    enabled: true,
                    style: {
                        color: "#FFFFFF",
                        textOutline: "1px contrast",
                        fontSize: "11px"
                    }
                },
                point: {
                    events: {
                        click: function () {
                            if (this.options.reg_no) {
                                window.location.href = `/fund/${this.options.reg_no}`;
                            }
                        }
                    }
                }
            }],
            title: { text: null },
            tooltip: {
                useHTML: true,
                formatter: function () {
                    return `<b>${this.point.name}</b><br>
                            ارزش دارایی: ${(this.point.value / 10000000000).toFixed(0)} میلیارد تومان<br>
                            بازدهی 30 روزه: <b style="color:${this.point.colorValue > 0 ? 'green' : 'red'}">
                            ${this.point.colorValue}%</b>`;
                }
            }
        });

    } catch (error) {
        console.error("Heatmap loading failed:", error);
        container.innerHTML =
            `<div class="error-state text-center p-5 text-danger">دریافت اطلاعات Heatmap ناموفق بود.</div>`;
    }
}


async function loadMarketPulse() {
    try {
        const data = await fetchJSON("/api/dashboard/market-pulse");

        const setText = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        };

        setText("pulse_total", data.total);
        setText("pulse_positive", data.positive + " ↑");
        setText("pulse_negative", data.negative + " ↓");
        setText("pulse_unchanged", data.unchanged);

        setText("breadth_text", data.breadth + "%");
        setText("vol_text", data.up_volume_ratio + "%");
        setText("total_trades_txt", "Trades: " + Number(data.total_trades || 0).toLocaleString());

        const breadthBar = document.getElementById("breadth_bar");
        if (breadthBar) {
            breadthBar.style.width = Math.min(100, Math.max(0, data.breadth)) + "%";
        }

        const volumeBar = document.getElementById("vol_bar");
        if (volumeBar) {
            volumeBar.style.width = Math.min(100, Math.max(0, data.up_volume_ratio)) + "%";
        }

    } catch (error) {
        console.error("Market pulse loading failed:", error);
    }
}


document.addEventListener("DOMContentLoaded", () => {
    loadTopFunds();
    loadHeatmap();
    loadMarketPulse();
    setInterval(loadMarketPulse, 60000);
});