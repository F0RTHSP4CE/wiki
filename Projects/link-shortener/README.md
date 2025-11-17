---
title: Link Shortener
description: go.f0rth.space link shortener
published: true
date: 2025-06-28T16:55:49.620Z
tags: 
editor: markdown
dateCreated: 2025-06-25T23:16:30.177Z
---

# go.f0rth.space Link Shortener

### 1. Authentication

To access the admin panel login via LDAP (OpenID Connect) or open the secret authentication URL.
-   **Location:** Find the URL in the internal Bitwarden vault (search for "go.f0rth.space").
-   **Action:** Visiting the URL sets a 24-hour access cookie and redirects you to the admin panel.

### 2. Link Management

-   **Create / Update:**
    -   Use the form at the top of the admin panel.
    -   A new slug creates a new link. An existing slug updates the destination URL.

-   **Delete:**
    -   Click the "Delete" button next to the link in the list.

### 3. Usage Format

-   **URL Structure:** `https://go.f0rth.space/your-slug`

### 4. Source code

https://gist.github.com/cofob/e0c9e8fd51a8b1c456b5441051251d9e

Hosted on Cloudflare Worker `link-shortener` in main Cloudflare account.
