import io
import re
import markdown
from bs4 import BeautifulSoup
from xhtml2pdf import pisa

def format_tables_for_pdf(html_content: str) -> str:
    """
    Post-processes HTML to inject explicit column widths and formatting for xhtml2pdf.
    Prevents crushed table columns, text overlap, and broken layouts.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    for table in soup.find_all('table'):
        table['style'] = "width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 7.5pt; page-break-inside: avoid;"
        table['cellpadding'] = "4"
        table['cellspacing'] = "0"
        
        header_row = table.find('tr')
        if not header_row:
            continue
        cols = header_row.find_all(['th', 'td'])
        num_cols = len(cols)
        
        if num_cols == 2:
            widths = ["30%", "70%"]
        elif num_cols == 3:
            widths = ["25%", "35%", "40%"]
        elif num_cols == 4:
            widths = ["20%", "18%", "34%", "28%"]
        elif num_cols == 5:
            widths = ["16%", "14%", "26%", "22%", "22%"]
        else:
            pct = f"{int(100 / max(num_cols, 1))}%"
            widths = [pct] * num_cols
            
        for row in table.find_all('tr'):
            cells = row.find_all(['th', 'td'])
            for i, cell in enumerate(cells):
                if i < len(widths):
                    cell['width'] = widths[i]
                    is_header = (cell.name == 'th')
                    cell['style'] = (
                        f"width: {widths[i]}; border: 1px solid #cbd5e1; padding: 4px 6px; "
                        f"vertical-align: top; word-wrap: break-word; font-size: 7.5pt; "
                        f"{'font-weight: bold; background-color: #f1f5f9; color: #0f172a;' if is_header else 'color: #334155;'}"
                    )

    # Post-process blockquotes
    for bq in soup.find_all('blockquote'):
        bq['style'] = "border-left: 3.5px solid #4f46e5; background-color: #f8fafc; padding: 6px 10px; margin: 6px 0; color: #475569; font-style: italic; font-size: 8pt; page-break-inside: avoid;"

    # Post-process code blocks
    for pre in soup.find_all('pre'):
        pre['style'] = "background-color: #090d16; color: #38bdf8; border: 1px solid #1e293b; padding: 6px 8px; font-family: Courier, monospace; font-size: 7.5pt; margin: 6px 0; border-radius: 4px; page-break-inside: avoid; white-space: pre-wrap;"
        
    return str(soup)

def generate_lesson_pdf(title: str, domain: str, tier: str, sections: list) -> bytes:
    """
    Converts complete masterclass lesson content into an official, formal Study Guide PDF.
    """
    body_html_parts = []
    for idx, sec in enumerate(sections):
        title_text = sec.get("title", f"Section {idx + 1}")
        raw_md = sec.get("content", "")
        example = sec.get("example", "")
        
        # Clean markdown: replace raw mermaid with a clean callout block for PDF
        cleaned_md = re.sub(
            r"```mermaid[\s\S]*?```", 
            "\n> **📊 Visual Architecture**: Interactive vector flowchart available in the web masterclass.\n", 
            raw_md
        )
        raw_html = markdown.markdown(cleaned_md, extensions=['extra', 'tables', 'fenced_code', 'nl2br'])
        html_section = format_tables_for_pdf(raw_html)
        
        example_block = ""
        if example:
            example_block = f"""
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-left: 3.5px solid #4f46e5; padding: 8px 10px; margin-top: 10px; border-radius: 4px; page-break-inside: avoid;">
                <p style="font-weight: bold; color: #3730a3; margin: 0 0 4px 0; font-size: 8pt; text-transform: uppercase; letter-spacing: 0.5px;">💻 Worked Code Implementation:</p>
                <pre style="margin: 0; font-size: 7.5pt; font-family: Courier, monospace; white-space: pre-wrap; background-color: #090d16; color: #38bdf8; padding: 6px; border-radius: 3px;">{example}</pre>
            </div>
            """
            
        body_html_parts.append(f"""
        <div style="margin-bottom: 20px;">
            <div style="background-color: #f1f5f9; border-left: 4px solid #4f46e5; padding: 4px 8px; margin-top: 16px; margin-bottom: 8px; page-break-after: avoid;">
                <h2 style="color: #1e1b4b; font-size: 11pt; margin: 0; padding: 0; font-weight: bold;">
                    Section {idx + 1}: {title_text}
                </h2>
            </div>
            <div style="font-size: 8.5pt; color: #334155; line-height: 1.45;">
                {html_section}
            </div>
            {example_block}
        </div>
        """)

    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: a4 portrait;
        margin: 1.4cm 1.2cm 1.4cm 1.2cm;
        @frame footer_frame {{
            -pdf-frame-content: footer_content;
            bottom: 0.5cm;
            left: 1.2cm;
            right: 1.2cm;
            height: 0.6cm;
        }}
    }}
    body {{
        font-family: Helvetica, Arial, sans-serif;
        color: #1e293b;
        font-size: 8.5pt;
        line-height: 1.45;
    }}
    .formal-header {{
        border-bottom: 2px solid #4f46e5;
        padding-bottom: 8px;
        margin-bottom: 12px;
    }}
    .org-badge {{
        font-size: 7pt;
        font-weight: bold;
        color: #4f46e5;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 2px;
    }}
    h1 {{
        color: #0f172a;
        font-size: 16pt;
        margin: 2px 0 4px 0;
        font-weight: bold;
    }}
    .doc-subtitle {{
        color: #475569;
        font-size: 8.5pt;
        margin: 0 0 6px 0;
        font-weight: 500;
    }}
    .meta-table {{
        width: 100%;
        border-collapse: collapse;
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        margin-top: 4px;
    }}
    .meta-table td {{
        padding: 4px 8px;
        font-size: 7.5pt;
        border: 1px solid #e2e8f0;
        color: #334155;
    }}
    h2 {{
        color: #1e1b4b;
        page-break-after: avoid;
    }}
    h3 {{
        color: #312e81;
        font-size: 9.5pt;
        margin-top: 10px;
        margin-bottom: 4px;
        font-weight: bold;
        page-break-after: avoid;
    }}
    p {{
        margin-bottom: 6px;
    }}
    ul, ol {{
        margin-left: 16px;
        margin-bottom: 6px;
    }}
    li {{
        margin-bottom: 2px;
    }}
    code {{
        font-family: Courier, monospace;
        font-size: 8pt;
        background-color: #f1f5f9;
        color: #0f172a;
        padding: 1px 3px;
        border-radius: 2px;
    }}
</style>
</head>
<body>
    <div id="footer_content" style="text-align: right; font-size: 7pt; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 2px;">
        Diva AI Computer Science Academy &bull; Official Study Guide &bull; Page <pdf:pagenumber> of <pdf:pagecount>
    </div>

    <div class="formal-header">
        <div class="org-badge">DIVA AI &bull; COMPUTER SCIENCE ACADEMY</div>
        <h1>{title}</h1>
        <div class="doc-subtitle">Official Masterclass Study Guide &amp; Technical Reference Manual</div>
        <table class="meta-table">
            <tr>
                <td><strong>Domain:</strong> {domain}</td>
                <td><strong>Curriculum Level:</strong> {tier}</td>
                <td><strong>Format:</strong> 50-Min Masterclass</td>
                <td><strong>Publisher:</strong> Diva AI Learning Platform</td>
            </tr>
        </table>
    </div>

    {''.join(body_html_parts)}
</body>
</html>
"""
    output = io.BytesIO()
    pisa_status = pisa.CreatePDF(src=full_html, dest=output, encoding='utf-8')
    if pisa_status.err:
        raise Exception(f"xhtml2pdf error code: {pisa_status.err}")
    return output.getvalue()

def generate_roadmap_pdf(domain: str, detected_level: str, roadmap: list) -> bytes:
    """
    Converts complete course roadmap curriculum into a publication-quality binary PDF.
    """
    modules_html = []
    for idx, mod in enumerate(roadmap):
        mod_title = mod.get("title", f"Module {idx + 1}")
        tier = mod.get("tier", "All Levels")
        is_rev = mod.get("isRevision", False)
        desc = mod.get("description", "")
        lessons = mod.get("lessons", [])
        
        rev_badge = '<span style="color: #4338ca; font-weight: bold;">[Revision Module]</span>' if is_rev else ''
        
        lessons_li = []
        for l_idx, lesson in enumerate(lessons):
            l_title = lesson.get("title", f"Lesson {l_idx + 1}")
            skill_id = lesson.get("targetSkillId", "")
            lessons_li.append(f"""
            <li style="margin-bottom: 3px;">
                <strong>{l_title}</strong> 
                <span style="color: #64748b; font-size: 7.5pt;">(Target Skill: {skill_id})</span>
            </li>
            """)
            
        modules_html.append(f"""
        <div style="margin-bottom: 14px; padding: 8px 12px; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; page-break-inside: avoid;">
            <h2 style="color: #1e1b4b; font-size: 10pt; margin: 0 0 3px 0;">Module {idx + 1}: {mod_title} {rev_badge}</h2>
            <p style="color: #475569; font-size: 8pt; margin: 0 0 6px 0;"><strong>Tier:</strong> {tier} &nbsp;|&nbsp; {desc}</p>
            <h3 style="color: #3730a3; font-size: 8.5pt; margin: 4px 0 3px 0;">Lessons & Mastery Milestones:</h3>
            <ul style="margin-left: 14px; font-size: 8pt; color: #334155; margin-bottom: 0;">
                {''.join(lessons_li)}
            </ul>
        </div>
        """)

    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: a4 portrait;
        margin: 1.4cm 1.2cm 1.4cm 1.2cm;
        @frame footer_frame {{
            -pdf-frame-content: footer_content;
            bottom: 0.5cm;
            left: 1.2cm;
            right: 1.2cm;
            height: 0.6cm;
        }}
    }}
    body {{
        font-family: Helvetica, Arial, sans-serif;
        color: #1e293b;
        font-size: 8.5pt;
        line-height: 1.45;
    }}
    h1 {{
        color: #0f172a;
        font-size: 16pt;
        border-bottom: 2px solid #4f46e5;
        padding-bottom: 4px;
        margin-bottom: 6px;
    }}
    .badge {{
        background-color: #e0e7ff;
        color: #3730a3;
        padding: 2px 6px;
        font-size: 7pt;
        font-weight: bold;
        border-radius: 2px;
        letter-spacing: 0.5px;
    }}
</style>
</head>
<body>
    <div id="footer_content" style="text-align: right; font-size: 7pt; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 2px;">
        Diva AI Computer Science Academy &bull; Complete Curriculum &bull; Page <pdf:pagenumber> of <pdf:pagecount>
    </div>

    <div style="margin-bottom: 12px;">
        <span class="badge">DIVA AI COMPLETE COURSE CURRICULUM</span>
        <h1 style="margin-top: 4px;">{domain} — Complete Roadmap Curriculum</h1>
        <p style="color: #64748b; font-size: 8pt; margin: 0;">
            <strong>Domain:</strong> {domain} &nbsp;|&nbsp; 
            <strong>Assessed Level:</strong> {detected_level} &nbsp;|&nbsp; 
            <strong>Published:</strong> Diva AI Computer Science Platform
        </p>
    </div>
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin-bottom: 12px;">

    {''.join(modules_html)}
</body>
</html>
"""
    output = io.BytesIO()
    pisa_status = pisa.CreatePDF(src=full_html, dest=output, encoding='utf-8')
    if pisa_status.err:
        raise Exception(f"xhtml2pdf error code: {pisa_status.err}")
    return output.getvalue()
