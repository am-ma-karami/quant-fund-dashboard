async function fetchJSON(url) {
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(
            `${url} failed: ${response.status}`
        );
    }

    return response.json();
}


async function loadFundChart(regNo) {
    const chartContainer = document.getElementById('fundChart');
    const loadingEl = document.getElementById('chart-loading');
    const errorEl = document.getElementById('chart-error');
    const statusEl = document.getElementById('chart-status');

    try {
        loadingEl.style.display = 'block';
        errorEl.style.display = 'none';
        chartContainer.style.display = 'none';

        const data = await fetchJSON(`/api/fund/${regNo}/chart`);

        if (!data.history || !data.history.length) {
            loadingEl.style.display = 'none';
            const latest = data.latest_history_at
                ? new Date(data.latest_history_at).toLocaleDateString('fa-IR')
                : 'نامشخص';
            errorEl.textContent = `داده‌ای در ۳۰ روز اخیر موجود نیست. آخرین داده: ${latest}`;
            errorEl.style.display = 'block';
            return;
        }

        loadingEl.style.display = 'none';
        chartContainer.style.display = 'block';
        const points = data.history
            .map(h => [Date.parse(h.timestamp), Number(h.nav_stat || 0)])
            .filter(([timestamp, value]) => !Number.isNaN(timestamp) && Number.isFinite(value))
            .sort((first, second) => first[0] - second[0]);

        if (!points.length) {
            throw new Error('Chart API returned no valid NAV observations.');
        }
        statusEl.textContent = data.has_changes_in_window
            ? 'تغییرات NAV در ۳۰ روز اخیر — بروزرسانی خودکار هر ۶۰ ثانیه'
            : 'در ۳۰ روز اخیر تغییری از منبع ثبت نشده؛ مقدار NAV تا زمان دریافت آخرین snapshot حفظ شده است.';
        statusEl.className = `small mb-2 ${data.has_changes_in_window ? 'text-success' : 'text-muted'}`;
        statusEl.style.display = 'block';
        renderInteractiveFundChart(chartContainer, points, 30);

        // Update last updated time
        if (data.fund && data.fund.last_updated) {
            const lastUpdated = new Date(data.fund.last_updated);
            document.getElementById('last_updated').textContent = lastUpdated.toLocaleTimeString('fa-IR');
        }
        
        if (data.fund && data.fund.nav_stat) {
            document.getElementById('nav_stat').textContent = data.fund.nav_stat.toLocaleString();
        }

    } catch (error) {
        console.error("Fund chart loading failed:", error);
        loadingEl.style.display = 'none';
        errorEl.textContent = 'دریافت یا نمایش نمودار ناموفق بود. لطفاً دوباره تلاش کنید.';
        errorEl.style.display = 'block';
    }
}

function renderInteractiveFundChart(container, points, defaultDays) {
    const ranges = [{ label: '۷ روز', days: 7 }, { label: '۳۰ روز', days: 30 }, { label: 'همه', days: null }];
    const width = 760;
    const height = 330;
    const padding = { top: 22, right: 24, bottom: 44, left: 86 };
    const ns = 'http://www.w3.org/2000/svg';
    const formatDate = timestamp => new Date(timestamp).toLocaleDateString('fa-IR');
    const formatValue = value => Math.round(value).toLocaleString('fa-IR');

    const draw = days => {
        const latest = points.at(-1)[0];
        const visible = days ? points.filter(([timestamp]) => timestamp >= latest - days * 86400000) : points;
        const data = visible.length ? visible : points.slice(-1);
        container.replaceChildren();

        const controls = document.createElement('div');
        controls.className = 'btn-group btn-group-sm mb-2';
        controls.setAttribute('role', 'group');
        ranges.forEach(range => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `btn ${range.days === days ? 'btn-primary' : 'btn-outline-primary'}`;
            button.textContent = range.label;
            button.addEventListener('click', () => draw(range.days));
            controls.appendChild(button);
        });

        const chart = document.createElement('div');
        chart.className = 'position-relative';
        const svg = document.createElementNS(ns, 'svg');
        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.setAttribute('role', 'img');
        svg.setAttribute('aria-label', 'نمودار تغییرات NAV');
        svg.style.width = '100%';
        svg.style.height = '350px';

        const values = data.map(([, value]) => value);
        const rawMin = Math.min(...values);
        const rawMax = Math.max(...values);
        const valuePadding = Math.max((rawMax - rawMin) * 0.12, rawMax * 0.01, 1);
        const minValue = rawMin - valuePadding;
        const maxValue = rawMax + valuePadding;
        const plotWidth = width - padding.left - padding.right;
        const plotHeight = height - padding.top - padding.bottom;
        const firstTime = data[0][0];
        const lastTime = data.at(-1)[0];
        const xFor = timestamp => data.length === 1 ? padding.left + plotWidth / 2 : padding.left + ((timestamp - firstTime) / (lastTime - firstTime)) * plotWidth;
        const yFor = value => padding.top + ((maxValue - value) / (maxValue - minValue)) * plotHeight;
        const append = (tag, attributes = {}) => {
            const element = document.createElementNS(ns, tag);
            Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
            svg.appendChild(element);
            return element;
        };

        for (let index = 0; index <= 4; index += 1) {
            const y = padding.top + (plotHeight * index) / 4;
            const value = maxValue - ((maxValue - minValue) * index) / 4;
            append('line', { x1: padding.left, y1: y, x2: width - padding.right, y2: y, stroke: '#e9ecef' });
            const label = append('text', { x: padding.left - 8, y: y + 4, 'text-anchor': 'end', fill: '#6c757d', 'font-size': '11' });
            label.textContent = formatValue(value);
        }

        const line = data.map(([timestamp, value], index) => {
            if (!index) return `M ${xFor(timestamp)} ${yFor(value)}`;
            const previousValue = data[index - 1][1];
            return `L ${xFor(timestamp)} ${yFor(previousValue)} L ${xFor(timestamp)} ${yFor(value)}`;
        }).join(' ');
        const area = `${line} L ${xFor(data.at(-1)[0])} ${padding.top + plotHeight} L ${xFor(data[0][0])} ${padding.top + plotHeight} Z`;
        append('path', { d: area, fill: 'rgba(37, 99, 235, 0.14)' });
        append('path', { d: line, fill: 'none', stroke: '#2563eb', 'stroke-width': '2.5', 'stroke-linejoin': 'round' });
        [data[0], data.at(-1)].forEach(([timestamp], index) => {
            const label = append('text', { x: xFor(timestamp), y: height - 14, 'text-anchor': index ? 'end' : 'start', fill: '#6c757d', 'font-size': '11' });
            label.textContent = formatDate(timestamp);
        });

        const crosshair = append('line', { y1: padding.top, y2: padding.top + plotHeight, stroke: '#94a3b8', 'stroke-dasharray': '4 4', visibility: 'hidden' });
        const marker = append('circle', { r: '5', fill: '#fff', stroke: '#2563eb', 'stroke-width': '2', visibility: 'hidden' });
        const tooltip = document.createElement('div');
        tooltip.className = 'position-absolute bg-dark text-white rounded px-2 py-1 small shadow';
        tooltip.style.cssText += ';display:none;pointer-events:none;z-index:1;';
        const overlay = append('rect', { x: padding.left, y: padding.top, width: plotWidth, height: plotHeight, fill: 'transparent' });
        overlay.addEventListener('mousemove', event => {
            const rect = svg.getBoundingClientRect();
            const x = ((event.clientX - rect.left) / rect.width) * width;
            const nearest = data.reduce((current, point) => Math.abs(xFor(point[0]) - x) < Math.abs(xFor(current[0]) - x) ? point : current);
            const pointX = xFor(nearest[0]);
            const pointY = yFor(nearest[1]);
            crosshair.setAttribute('x1', pointX); crosshair.setAttribute('x2', pointX); crosshair.setAttribute('visibility', 'visible');
            marker.setAttribute('cx', pointX); marker.setAttribute('cy', pointY); marker.setAttribute('visibility', 'visible');
            tooltip.textContent = `${formatDate(nearest[0])} | NAV: ${formatValue(nearest[1])} ریال`;
            tooltip.style.display = 'block'; tooltip.style.left = `${Math.min(event.offsetX + 12, chart.clientWidth - 190)}px`; tooltip.style.top = `${Math.max(event.offsetY - 34, 0)}px`;
        });
        overlay.addEventListener('mouseleave', () => { crosshair.setAttribute('visibility', 'hidden'); marker.setAttribute('visibility', 'hidden'); tooltip.style.display = 'none'; });
        chart.append(svg, tooltip);
        container.append(controls, chart);
    };
    draw(defaultDays);
}


document.addEventListener(
    "DOMContentLoaded",
    () => {
        const fundDataEl = document.getElementById('fund-data');
        const regNo = fundDataEl ? fundDataEl.dataset.regNo : null;
        if (regNo) {
            loadFundChart(regNo);
            setInterval(() => loadFundChart(regNo), 60000);
        }
    }
);
