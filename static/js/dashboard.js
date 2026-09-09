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
    if (!container) {
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

        const maximum = Math.max(...data.map(item => Math.abs(Number(item.return_30d || 0))), 1);
        const list = document.createElement("div");
        list.className = "row row-cols-1 row-cols-md-2 g-3";

        data.forEach(item => {
            const value = Number(item.return_30d || 0);
            const positive = value >= 0;
            const column = document.createElement("div");
            column.className = "col";
            const link = document.createElement("a");
            link.href = `/fund/${item.reg_no}`;
            link.className = "card h-100 border-0 bg-light text-decoration-none shadow-sm";
            const body = document.createElement("div");
            body.className = "card-body py-3";
            const header = document.createElement("div");
            header.className = "d-flex align-items-center gap-2 mb-2";
            const rank = document.createElement("span");
            rank.className = "badge rounded-pill bg-primary";
            rank.textContent = item.rank;
            const name = document.createElement("span");
            name.className = "text-dark fw-semibold text-truncate";
            name.textContent = item.name;
            header.append(rank, name);
            const metrics = document.createElement("div");
            metrics.className = "d-flex justify-content-between align-items-center small";
            const label = document.createElement("span");
            label.className = "text-muted";
            label.textContent = "بازدهی ۳۰ روزه";
            const returnValue = document.createElement("span");
            returnValue.dir = "ltr";
            returnValue.className = `fw-bold ${positive ? "text-success" : "text-danger"}`;
            returnValue.textContent = `${positive ? "+" : ""}${value.toLocaleString("fa-IR", { maximumFractionDigits: 2 })}%`;
            metrics.append(label, returnValue);
            const progress = document.createElement("div");
            progress.className = "progress mt-2";
            progress.style.height = "5px";
            const bar = document.createElement("div");
            bar.className = `progress-bar ${positive ? "bg-success" : "bg-danger"}`;
            bar.style.width = `${Math.min(100, (Math.abs(value) / maximum) * 100)}%`;
            progress.appendChild(bar);
            body.append(header, metrics, progress);
            link.appendChild(body);
            column.appendChild(link);
            list.appendChild(column);
        });
        container.replaceChildren(list);

    } catch (error) {
        console.error("Top funds loading failed:", error);
        container.style.display = "block";
        container.innerHTML =
            `<div class="error-state text-center p-3 text-danger">دریافت اطلاعات Top 10 ناموفق بود.</div>`;
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


async function loadDataQuality() {
    try {
        const data = await fetchJSON("/api/health/data");

        const setText = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        };

        setText("dq_status", data.status);
        setText("dq_expected", data.expected_funds);
        setText("dq_received", data.received_funds);
        setText("dq_coverage", (data.coverage * 100).toFixed(1) + "%");

        const statusEl = document.getElementById("dq_status");
        if (statusEl) {
            statusEl.className = `fs-5 fw-bold ${
                data.status === "healthy" ? "text-success" :
                data.status === "partial" ? "text-warning" : "text-danger"
            }`;
        }

    } catch (error) {
        console.error("Data quality loading failed:", error);
    }
}


async function loadRiskReturn() {
    const container = document.getElementById("risk-return-container");
    if (!container) {
        return;
    }

    try {
        const data = await fetchJSON("/api/dashboard/risk-return");

        if (!data.length) {
            container.innerHTML =
                `<div class="empty-state text-center p-5 text-muted">داده‌ای برای نقشه ریسک/بازده موجود نیست.</div>`;
            return;
        }

        const maxAum = Math.max(...data.map(item => item.aum || 0), 1);
        const points = data.map(item => ({
            x: item.volatility,
            y: item.return_90d,
            r: 3 + 11 * Math.sqrt((item.aum || 0) / maxAum),
            reg_no: item.reg_no,
            name: item.name,
            aum: item.aum,
            volatility: item.volatility,
            return_90d: item.return_90d,
        }));

        if (window.riskReturnChart) {
            window.riskReturnChart.destroy();
        }

        window.riskReturnChart = new Chart(container, {
            type: "bubble",
            data: {
                datasets: [{
                    label: "صندوق‌های سهامی",
                    data: points,
                    backgroundColor: points.map(p =>
                        p.y >= 0
                            ? "rgba(25, 135, 84, 0.45)"
                            : "rgba(220, 53, 69, 0.45)"
                    ),
                    borderColor: points.map(p =>
                        p.y >= 0 ? "#198754" : "#dc3545"
                    ),
                    borderWidth: 1,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        title: { display: true, text: "نوسان سالانه (%)", font: { family: "Tahoma" } },
                        ticks: { font: { family: "Tahoma" } },
                    },
                    y: {
                        title: { display: true, text: "بازده ۹۰ روزه (%)", font: { family: "Tahoma" } },
                        ticks: { font: { family: "Tahoma" } },
                    },
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: items => items[0].raw.name || "",
                            label: item => [
                                "بازده ۹۰ روزه: " + item.raw.return_90d + "%",
                                "نوسان سالانه: " + item.raw.volatility + "%",
                                "ارزش دارایی: " + (item.raw.aum / 1e9).toFixed(1) + " میلیارد تومان",
                            ],
                        },
                    },
                },
                onClick: (event, elements) => {
                    if (elements.length) {
                        const index = elements[0].index;
                        window.location.href = `/fund/${points[index].reg_no}`;
                    }
                },
            },
        });

    } catch (error) {
        console.error("Risk/return loading failed:", error);
        container.innerHTML =
            `<div class="error-state text-center p-5 text-danger">دریافت نقشه ریسک/بازده ناموفق بود.</div>`;
    }
}


document.addEventListener("DOMContentLoaded", () => {
    loadTopFunds();
    loadHeatmap();
    loadMarketPulse();
    loadDataQuality();
    loadRiskReturn();
    setInterval(loadMarketPulse, 60000);
    setInterval(loadDataQuality, 60000);
});
