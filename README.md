# SEO Schema Generator (Render)

This is a small Flask app that accepts an Excel file (`.xlsx`) and returns an output Excel file with:
- Meta Title
- Meta Description
- Product Schema
- Breadcrumb Schema
- FAQ Schema
- Blog (Article) Schema

## Local Run

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000, upload your Excel file, and download the output.

## Render Deploy

1. Push this folder to a GitHub repo.
2. In Render, create a **New Web Service**.
3. Choose your repo.
4. Set:
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
5. Deploy and open the service URL.

## Excel Input Columns (Row 1)

These columns are required **except** where noted. The script will derive
`brand_name`, `site_name`, and `publisher_name` from the URL domain if they
are not provided. The `keywords` column is no longer used.

```
h1,url,product_name,product_url,product_image,product_description,rating_value,best_rating,review_author_name,faq_q1,faq_a1,faq_q2,faq_a2,faq_q3,faq_a3,blog_url,headline,blog_description,blog_image,author_name,publisher_logo,date_published,date_modified
```

Optional (auto-derived from URL if omitted):
- `brand_name`
- `site_name`
- `publisher_name`

Each row = one page.
