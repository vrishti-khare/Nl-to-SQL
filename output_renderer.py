"""
=============================================================
Output Renderer -- Visual Output for Wargame AI Assistant
=============================================================
Generates standalone HTML files for different output types:
  - MAP: Interactive Leaflet map with pins (folium)
  - LINE_CHART: Trend lines over time (plotly)
  - BAR_CHART: Comparisons between groups (plotly)
  - TIMELINE: Sequence of events (plotly)
  - TABLE: Clean formatted HTML table
  - TEXT: No visualization (terminal only)

All outputs are saved to D:\wargame-analysis\output\ and
auto-opened in the default browser.

Usage:
    from output_renderer import render_output
    render_output('map', columns, rows, question, answer)
=============================================================
"""

import os
import webbrowser
import datetime

# Output directory for generated HTML files
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def _ensure_output_dir():
    """Create the output directory if it doesn't exist."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def _save_and_open(html_content, filename):
    """Save HTML to file and open in browser."""
    _ensure_output_dir()
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    print("  [OUTPUT] Saved to: %s" % filepath)
    webbrowser.open("file:///" + filepath.replace("\\", "/"))
    return filepath


def _find_columns(columns, keywords):
    """Find column index by matching keywords in column names.
    Uses exact match or suffix match to prevent false positives
    (e.g., 'lat' matching 'platform_name')."""
    for i, col in enumerate(columns):
        col_lower = col.lower()
        for kw in keywords:
            # Exact match (e.g., 'latitude' == 'latitude')
            if col_lower == kw:
                return i
            # Suffix match with underscore boundary (e.g., 'detected_latitude' ends with '_latitude')
            if col_lower.endswith('_' + kw):
                return i
    return None


# =============================================================
# MAP RENDERER (folium / Leaflet.js)
# =============================================================
def render_map(columns, rows, question, answer):
    """
    Render latitude/longitude data as an interactive map.
    Auto-detects lat/lng columns. Limits to 500 points for performance.
    """
    import folium

    # Find lat/lng columns
    lat_idx = _find_columns(columns, ['lat', 'latitude'])
    lng_idx = _find_columns(columns, ['lng', 'lon', 'longitude'])

    if lat_idx is None or lng_idx is None:
        print("  [!] Cannot render map: no latitude/longitude columns found.")
        print("      Columns available: %s" % columns)
        render_table(columns, rows, question, answer)
        return

    # Limit rows for performance
    max_points = 500
    display_rows = rows[:max_points]
    truncated = len(rows) > max_points

    # Calculate map center from data
    lats = [float(row[lat_idx]) for row in display_rows if row[lat_idx] is not None]
    lngs = [float(row[lng_idx]) for row in display_rows if row[lng_idx] is not None]

    if not lats or not lngs:
        print("  [!] No valid coordinates found in data.")
        render_table(columns, rows, question, answer)
        return

    center_lat = sum(lats) / len(lats)
    center_lng = sum(lngs) / len(lngs)

    # Create the map
    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=8,
        tiles="OpenStreetMap"
    )

    # Force-name to color mapping
    force_color_map = {
        'red': '#e74c3c',       # Red
        'blue': '#2980b9',      # Blue
        'green': '#27ae60',     # Green
        'yellow': '#f39c12',    # Orange-yellow (yellow is invisible on maps)
    }
    default_color = '#7f8c8d'   # Gray fallback

    # Detect force_name column index
    force_idx = _find_columns(columns, ['force_name'])

    # Track which forces appear (for legend)
    forces_seen = set()

    # Add markers for each point
    for i, row in enumerate(display_rows):
        lat = row[lat_idx]
        lng = row[lng_idx]
        if lat is None or lng is None:
            continue

        # Determine marker color from force_name
        marker_color = default_color
        if force_idx is not None and row[force_idx] is not None:
            force_lower = str(row[force_idx]).strip().lower()
            forces_seen.add(str(row[force_idx]).strip())
            for force_key, color in force_color_map.items():
                if force_key in force_lower:
                    marker_color = color
                    break
        else:
            # Fallback: Infer color from the user's question if force_name is missing
            q_lower = question.lower()
            for force_key, color in force_color_map.items():
                if force_key in q_lower:
                    marker_color = color
                    forces_seen.add(force_key.capitalize() + " (inferred)")
                    break

        # Build popup with all column data
        popup_lines = ["<b>Lat:</b> %s<br><b>Lng:</b> %s" % (lat, lng)]
        for j, col in enumerate(columns):
            if j != lat_idx and j != lng_idx:
                popup_lines.append("<b>%s:</b> %s" % (col, row[j]))
        
        popup_text = "<br>".join(popup_lines)

        folium.CircleMarker(
            location=[float(lat), float(lng)],
            radius=6,
            color=marker_color,
            weight=2,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.85,
            popup=folium.Popup(popup_text, max_width=300),
            tooltip=row[_find_columns(columns, ['platform_name', 'name'])] if _find_columns(columns, ['platform_name', 'name']) is not None else "Click for details"
        ).add_to(m)

    # Build legend HTML if we have force colors
    legend_html = ""
    if forces_seen:
        legend_items = ""
        for force_name in sorted(forces_seen):
            force_lower = force_name.lower()
            color = default_color
            for force_key, c in force_color_map.items():
                if force_key in force_lower:
                    color = c
                    break
            legend_items += '<div style="margin:4px 0;"><span style="display:inline-block;width:12px;height:12px;border-radius:50%%;background:%s;margin-right:8px;vertical-align:middle;"></span>%s</div>' % (color, force_name)

        legend_html = """
        <div style="position:fixed; bottom:30px; right:20px; z-index:9999;
                    background:rgba(255,255,255,0.95); padding:12px 16px;
                    border-radius:8px; font-family:Arial; font-size:13px;
                    box-shadow:0 2px 8px rgba(0,0,0,0.2);">
            <b>Forces</b><br>%s
        </div>
        """ % legend_items

    # Add title
    title_html = """
    <div style="position:fixed; top:10px; left:50%%; transform:translateX(-50%%);
                z-index:9999; background:rgba(0,0,0,0.8); color:white;
                padding:12px 24px; border-radius:8px; font-family:Arial;
                font-size:14px; max-width:80%%;">
        <b>🗺️ %s</b><br>
        <span style="font-size:12px; opacity:0.8;">%d points plotted%s</span>
    </div>
    """ % (
        question[:100],
        len(display_rows),
        " (showing first %d of %d)" % (max_points, len(rows)) if truncated else ""
    )
    m.get_root().html.add_child(folium.Element(title_html))
    if legend_html:
        m.get_root().html.add_child(folium.Element(legend_html))

    # Save and open
    _ensure_output_dir()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(OUTPUT_DIR, "map_%s.html" % timestamp)
    m.save(filepath)
    print("  [OUTPUT] Map saved to: %s" % filepath)
    webbrowser.open("file:///" + filepath.replace("\\", "/"))


# =============================================================
# LINE CHART RENDERER (plotly)
# =============================================================
def render_line_chart(columns, rows, question, answer):
    """
    Render trend data as a line chart.
    Auto-detects time/tick column for X-axis.
    """
    import plotly.graph_objects as go

    if not rows or not columns:
        print("  [!] No data to chart.")
        return

    # Find time/x-axis column
    x_idx = _find_columns(columns, ['tick', 'time', 'clock', 'timestamp', 'date'])
    if x_idx is None:
        x_idx = 0  # Default to first column

    # Limit rows
    max_rows = 1000
    display_rows = rows[:max_rows]

    x_values = [row[x_idx] for row in display_rows]

    # Plot all numeric columns as separate lines
    fig = go.Figure()
    for i, col in enumerate(columns):
        if i == x_idx:
            continue
        try:
            y_values = [float(row[i]) if row[i] is not None else None for row in display_rows]
            fig.add_trace(go.Scatter(
                x=x_values, y=y_values,
                mode='lines+markers',
                name=col,
                line=dict(width=2),
                marker=dict(size=3)
            ))
        except (ValueError, TypeError):
            continue  # Skip non-numeric columns

    fig.update_layout(
        title=dict(text="📈 %s" % question[:80], font=dict(size=16)),
        xaxis_title=columns[x_idx],
        yaxis_title="Value",
        template="plotly_dark",
        font=dict(family="Arial"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(OUTPUT_DIR, "line_chart_%s.html" % timestamp)
    _ensure_output_dir()
    fig.write_html(filepath, include_plotlyjs=True)
    print("  [OUTPUT] Line chart saved to: %s" % filepath)
    webbrowser.open("file:///" + filepath.replace("\\", "/"))


# =============================================================
# BAR CHART RENDERER (plotly)
# =============================================================
def render_bar_chart(columns, rows, question, answer):
    """
    Render comparison data as a bar chart.
    First column = labels, remaining numeric columns = values.
    """
    import plotly.graph_objects as go

    if not rows or not columns:
        print("  [!] No data to chart.")
        return

    labels = [str(row[0]) for row in rows]

    fig = go.Figure()
    colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6',
              '#1abc9c', '#e67e22', '#34495e']

    for i, col in enumerate(columns[1:], 1):
        try:
            values = [float(row[i]) if row[i] is not None else 0 for row in rows]
            fig.add_trace(go.Bar(
                x=labels, y=values,
                name=col,
                marker_color=colors[(i - 1) % len(colors)],
            ))
        except (ValueError, TypeError):
            continue

    fig.update_layout(
        title=dict(text="📊 %s" % question[:80], font=dict(size=16)),
        xaxis_title=columns[0],
        yaxis_title="Value",
        template="plotly_dark",
        font=dict(family="Arial"),
        barmode='group',
    )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(OUTPUT_DIR, "bar_chart_%s.html" % timestamp)
    _ensure_output_dir()
    fig.write_html(filepath, include_plotlyjs=True)
    print("  [OUTPUT] Bar chart saved to: %s" % filepath)
    webbrowser.open("file:///" + filepath.replace("\\", "/"))


# =============================================================
# TIMELINE RENDERER (plotly)
# =============================================================
def render_timeline(columns, rows, question, answer):
    """
    Render events as a horizontal timeline.
    Auto-detects time and description columns.
    """
    import plotly.graph_objects as go

    if not rows or not columns:
        print("  [!] No data for timeline.")
        return

    # Find time column
    time_idx = _find_columns(columns, ['tick', 'time', 'clock', 'timestamp'])
    if time_idx is None:
        time_idx = 0

    # Find description/action column
    desc_idx = _find_columns(columns, ['action', 'event', 'description', 'type', 'message', 'name'])
    if desc_idx is None:
        desc_idx = 1 if len(columns) > 1 else 0

    # Limit rows
    max_events = 100
    display_rows = rows[:max_events]

    times = [str(row[time_idx]) for row in display_rows]
    events = [str(row[desc_idx]) for row in display_rows]

    # Build hover text with all columns
    hover_texts = []
    for row in display_rows:
        parts = ["%s: %s" % (columns[j], row[j]) for j in range(len(columns))]
        hover_texts.append("<br>".join(parts))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=times,
        y=[1] * len(times),
        mode='markers+text',
        marker=dict(size=12, color='#e74c3c', symbol='diamond'),
        text=events,
        textposition='top center',
        textfont=dict(size=9),
        hovertext=hover_texts,
        hoverinfo='text',
    ))

    fig.update_layout(
        title=dict(text="📅 %s" % question[:80], font=dict(size=16)),
        xaxis_title=columns[time_idx],
        template="plotly_dark",
        font=dict(family="Arial"),
        yaxis=dict(visible=False),
        showlegend=False,
        height=400,
    )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(OUTPUT_DIR, "timeline_%s.html" % timestamp)
    _ensure_output_dir()
    fig.write_html(filepath, include_plotlyjs=True)
    print("  [OUTPUT] Timeline saved to: %s" % filepath)
    webbrowser.open("file:///" + filepath.replace("\\", "/"))


# =============================================================
# TABLE RENDERER (pure HTML)
# =============================================================
def render_table(columns, rows, question, answer):
    """
    Render data as a clean, styled HTML table.
    """
    max_rows = 200
    display_rows = rows[:max_rows]
    truncated = len(rows) > max_rows

    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Query Results</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: #1a1a2e;
            color: #eee;
            padding: 30px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .question {
            background: linear-gradient(135deg, #16213e, #0f3460);
            padding: 20px 28px;
            border-radius: 12px;
            margin-bottom: 20px;
            font-size: 18px;
            border-left: 4px solid #e94560;
        }
        .answer {
            background: rgba(255,255,255,0.05);
            padding: 16px 24px;
            border-radius: 10px;
            margin-bottom: 24px;
            line-height: 1.6;
            font-size: 14px;
        }
        .stats {
            color: #888;
            font-size: 12px;
            margin-bottom: 16px;
        }
        table {
            width: 100%%;
            border-collapse: collapse;
            background: rgba(255,255,255,0.03);
            border-radius: 10px;
            overflow: hidden;
        }
        th {
            background: #0f3460;
            color: #e94560;
            padding: 12px 16px;
            text-align: left;
            font-size: 13px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        td {
            padding: 10px 16px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 13px;
        }
        tr:hover td { background: rgba(233, 69, 96, 0.1); }
        tr:nth-child(even) td { background: rgba(255,255,255,0.02); }
    </style>
</head>
<body>
    <div class="container">
        <div class="question">🔍 %s</div>
        <div class="answer">%s</div>
        <div class="stats">%d rows returned%s</div>
        <table>
            <thead><tr>%s</tr></thead>
            <tbody>%s</tbody>
        </table>
    </div>
</body>
</html>""" % (
        question,
        answer.replace("\n", "<br>") if answer else "No answer generated.",
        len(rows),
        " (showing first %d)" % max_rows if truncated else "",
        "".join("<th>%s</th>" % col for col in columns),
        "".join(
            "<tr>%s</tr>" % "".join("<td>%s</td>" % str(v) for v in row)
            for row in display_rows
        ),
    )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    _save_and_open(html, "table_%s.html" % timestamp)


# =============================================================
# MAIN DISPATCHER
# =============================================================
def render_output(output_type, columns, rows, question, answer):
    """
    Main dispatcher. Routes to the correct renderer based on output_type.

    Args:
        output_type: One of 'text', 'map', 'bar_chart', 'line_chart', 'timeline'
        columns: List of column names from SQL result.
        rows: List of row tuples from SQL result.
        question: The original user question.
        answer: The AI-generated text answer.
    """
    if not columns or not rows:
        print("  [OUTPUT] No data to visualize.")
        return

    print("\n  [6/6] Rendering %s output..." % output_type.upper())

    try:
        if output_type == 'map':
            render_map(columns, rows, question, answer)
        elif output_type == 'line_chart':
            render_line_chart(columns, rows, question, answer)
        elif output_type == 'bar_chart':
            render_bar_chart(columns, rows, question, answer)
        elif output_type == 'timeline':
            render_timeline(columns, rows, question, answer)
        elif output_type == 'table':
            render_table(columns, rows, question, answer)
        else:
            # 'text' -- no visualization needed, already printed in terminal
            print("  [OUTPUT] Text-only output (no visualization).")
    except Exception as e:
        print("  [!] Failed to render %s: %s" % (output_type, str(e)))
        print("  Falling back to table output...")
        try:
            render_table(columns, rows, question, answer)
        except Exception as e2:
            print("  [!] Table fallback also failed: %s" % str(e2))
