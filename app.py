"""Vûntric Linguistic Archive — local Streamlit application."""
from __future__ import annotations

import json
from collections import Counter

import streamlit as st

import storage as db

st.set_page_config(
    page_title="Vûntric Linguistic Archive",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)
db.initialize()

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1400px;}
h1, h2, h3 {letter-spacing: -0.018em;}
div[data-testid="stMetric"] {background: rgba(120,120,120,.065); border-radius: .75rem; padding: 1rem;}
.small-caption {color: #888; font-size: .86rem;}
</style>
""", unsafe_allow_html=True)

PAGES = ["Home", "Language Foundations", "Dictionary", "Categories", "Languages", "Import / Export"]
if "page" not in st.session_state:
    st.session_state.page = "Home"


def go(page, word_class=None, category=None, query=None):
    st.session_state.page = page
    if word_class is not None:
        st.session_state.dict_class = word_class
    if category is not None:
        st.session_state.dict_category = category
    if query is not None:
        st.session_state.dict_query = query
    st.rerun()


def notice_success(label):
    st.success(label)


def save(collection, data, ident=None):
    try:
        result = db.save_record(collection, data, ident)
    except Exception as exc:
        st.error(f"Could not save: {exc}")
        return None
    st.success("Saved to your local database.")
    return result


def counts_snapshot():
    return db.snapshot()


def sidebar(languages):
    st.sidebar.title("📖 Vûntric Archive")
    st.sidebar.caption("Local linguistic database")
    language_ids = [x["id"] for x in languages]
    labels = {x["id"]: x["name"] for x in languages}
    if st.session_state.get("language_id") not in language_ids:
        st.session_state.language_id = language_ids[0]
    st.sidebar.selectbox("Current language", language_ids,
                         format_func=lambda x: labels.get(x, x), key="language_id")
    st.sidebar.divider()
    for page in PAGES:
        icon = {"Home":"⌂", "Language Foundations":"◫", "Dictionary":"▤", "Categories":"☷",
                "Languages":"◎", "Import / Export":"⇄"}[page]
        if st.sidebar.button(f"{icon}  {page}", use_container_width=True,
                             type="primary" if st.session_state.page == page else "secondary"):
            go(page)
    st.sidebar.divider()
    st.sidebar.caption(f"Database revision: {db.revision()}")
    st.sidebar.caption("Stored locally • no internet required")


def category_selector(categories, key, multiple=False, allow_all=False, label="Semantic categories"):
    paths = db.category_path_map(categories)
    choices = [x["id"] for x in sorted(categories, key=lambda c: paths[c["id"]].casefold())]
    if allow_all:
        choices = ["all"] + choices
    fmt = lambda ident: "All categories" if ident == "all" else paths.get(ident, ident)
    if multiple:
        return st.multiselect(label, choices, format_func=fmt, key=key)
    if st.session_state.get(key) not in choices:
        st.session_state[key] = "all" if allow_all else (choices[0] if choices else None)
    return st.selectbox(label, choices, format_func=fmt, key=key)


def render_home(snapshot, language):
    st.title(language["name"])
    st.caption("Linguistic archive · Encyclopedia and categorized dictionary")
    language_entries = [x for x in snapshot["entries"] if x["language_id"] == language["id"]]
    foundations = [x for x in snapshot["foundations"] if x["language_id"] == language["id"]]
    cols = st.columns(3)
    cols[0].metric("Dictionary entries", len(language_entries))
    cols[1].metric("Foundation articles", len(foundations))
    cols[2].metric("Semantic categories", len(snapshot["categories"]))

    st.subheader("Search the archive")
    query = st.text_input("Search across words, meanings, categories and foundation articles",
                          placeholder="e.g. river, weapons, morphology...", label_visibility="collapsed")
    if query.strip():
        needle = query.casefold().strip()
        matches = [x for x in language_entries if needle in " ".join([
            x["lemma"], x["gloss"], x["definition"], x["etymology"], x["notes"]]).casefold()]
        matching_classes = [x for x in snapshot["word_classes"] if needle in x["name"].casefold()]
        matching_categories = [x for x in snapshot["categories"] if needle in x["name"].casefold()]
        matching_foundations = [x for x in foundations if needle in (x["title"]+" "+x["content"]).casefold()]
        st.caption(f"{len(matches)} words · {len(matching_classes)} word classes · {len(matching_categories)} categories · {len(matching_foundations)} foundation articles")
        for entry in matches[:12]:
            if st.button(f"{entry['lemma']} — {entry['gloss'] or entry['definition'][:60] or 'No definition'}", key="search_"+entry["id"], use_container_width=True):
                st.session_state.open_entry = entry["id"]
                go("Dictionary", query=entry["lemma"])
        for word_class in matching_classes[:8]:
            if st.button("Word class: " + word_class["name"], key="wc_" + word_class["id"]):
                go("Dictionary", word_class=word_class["id"], category="all", query="")
        for category in matching_categories[:8]:
            if st.button("Category: " + category["name"], key="cat_" + category["id"]):
                go("Dictionary", word_class="all", category=category["id"], query="")
        for article in matching_foundations[:8]:
            if st.button("Foundation: " + article["title"], key="found_" + article["id"]):
                st.session_state.foundation_pick = article["id"]
                go("Language Foundations")
        st.divider()

    st.subheader("I. Language Foundations")
    st.caption("Writing system, sounds, morphology, sentence structure and editorial conventions.")
    names = ["Alphabet & Orthography", "Phonology & Phonotactics", "Morphology", "Syntax", "Grammar Overview", "Writing Conventions"]
    foundation_descriptions = {
        "Alphabet & Orthography": "29-letter working alphabet; Æ and long vowels",
        "Phonology & Phonotactics": "Sound values, stress and unresolved phonetics",
        "Morphology": "Word formation, noun inflection, gender and verb forms",
        "Syntax": "V2 statements, V1 questions, clauses and tense",
        "Grammar Overview": "Core grammatical rules and reference statuses",
        "Writing Conventions": "Spelling, capitalization and editorial policy",
    }
    for idx in range(0, len(names), 3):
        columns = st.columns(3)
        for col, title in zip(columns, names[idx:idx + 3]):
            article = next((x for x in foundations if x["title"] == title), None)
            with col:
                with st.container(border=True):
                    st.markdown(f"**{title}**")
                    if article and article["content"].strip():
                        st.caption(foundation_descriptions[title])
                    else:
                        st.caption("Not yet documented")
                    if st.button("Open article", key="foundation_card_" + title, use_container_width=True):
                        if article:
                            st.session_state.foundation_pick = article["id"]
                        go("Language Foundations")

    st.subheader("II. Word Classes")
    st.caption("Select a word class, then narrow by semantic category.")
    classes = snapshot["word_classes"]
    for idx in range(0, len(classes), 4):
        columns = st.columns(4)
        for col, word_class in zip(columns, classes[idx:idx + 4]):
            with col:
                count = sum(x["word_class_id"] == word_class["id"] for x in language_entries)
                if st.button(f"{word_class['name']}  ·  {count}", key="class_card_"+word_class["id"], use_container_width=True):
                    go("Dictionary", word_class=word_class["id"], category="all", query="")

    st.subheader("III. Browse Semantic Categories")
    st.caption("Words can belong to several subject categories without being duplicated.")
    categories = snapshot["categories"]
    children = {}
    for x in categories:
        children.setdefault(x["parent_id"], []).append(x)
    for root in sorted(children.get(None, []), key=lambda x:x["sort_order"]):
        with st.expander(root["name"]):
            if st.button("Browse all " + root["name"], key="browse_"+root["id"]):
                go("Dictionary", word_class="all", category=root["id"], query="")
            for child in sorted(children.get(root["id"], []), key=lambda x:x["sort_order"]):
                if st.button("↳ " + child["name"], key="browse_"+child["id"]):
                    go("Dictionary", word_class="all", category=child["id"], query="")


def render_foundations(snapshot, language):
    requested = st.session_state.pop("requested_foundation_id", None)
    if requested:
        st.session_state.foundation_pick = requested
    st.title("Language Foundations")
    st.caption("Browse grammar and writing-system articles. Editing is available in the separate Edit tab.")
    articles = sorted([x for x in snapshot["foundations"] if x["language_id"] == language["id"]], key=lambda x:(x["sort_order"],x["title"]))
    if not articles:
        st.info("This language has no articles yet.")
    else:
        choices = [x["id"] for x in articles]
        if st.session_state.get("foundation_pick") not in choices:
            st.session_state.foundation_pick = choices[0]
        chosen_id = st.selectbox("Foundation article", choices,
                                  format_func=lambda x:next(a["title"] for a in articles if a["id"]==x),
                                  key="foundation_pick")
        chosen = next(x for x in articles if x["id"]==chosen_id)
        read_tab, edit_tab = st.tabs(["📖 Read article", "✏️ Edit article"])
        with read_tab:
            with st.container(border=True):
                if chosen["content"].strip():
                    # Preserve any heading already supplied in the article itself.
                    if not chosen["content"].lstrip().startswith("#"):
                        st.subheader(chosen["title"])
                    st.markdown(chosen["content"])
                else:
                    st.subheader(chosen["title"])
                    st.info("No content documented yet. Open the Edit article tab to add it.")
        with edit_tab:
            with st.form("edit_foundation_" + chosen_id):
                title = st.text_input("Article title", value=chosen["title"])
                content = st.text_area("Article content (Markdown)", value=chosen["content"], height=480,
                                       help="Write paragraphs, headings, tables and examples in Markdown.")
                if st.form_submit_button("Save article", type="primary"):
                    if title.strip() and save("foundations", {"title":title.strip(),"content":content}, chosen_id):
                        st.rerun()
    with st.expander("+ Add a foundation or grammar article", expanded=False):
        with st.form("add_foundation"):
            new_title = st.text_input("New article title")
            new_text = st.text_area("Initial content", height=140)
            if st.form_submit_button("Create article"):
                if not new_title.strip():
                    st.warning("Give the article a title.")
                else:
                    ident = save("foundations", {"language_id": language["id"], "title": new_title.strip(),
                                                   "content": new_text, "sort_order": len(articles)})
                    if ident:
                        st.session_state.requested_foundation_id = ident
                        st.rerun()


def category_descendants(category_id, categories):
    descendants = {category_id}
    while True:
        extended = descendants | {x["id"] for x in categories if x["parent_id"] in descendants}
        if extended == descendants:
            break
        descendants = extended
    return descendants



def render_entry_readonly(entry, class_label, category_labels):
    """Reader-friendly entry display. Reserve status badges for exceptional states."""
    st.header(entry["lemma"])
    metadata = [class_label]
    if entry["ipa"].strip():
        metadata.append(entry["ipa"].strip())
    if entry["status"] != "established":
        metadata.append(entry["status"].capitalize())
    st.caption(" · ".join(metadata))

    gloss = entry["gloss"].strip()
    definition = entry["definition"].strip()
    if gloss:
        st.markdown(f"**{gloss}**")
    # Older entries may still have an identical gloss and definition. Don't echo it.
    if definition and (not gloss or definition.casefold() != gloss.casefold()):
        st.markdown(definition)

    if entry["category_ids"]:
        st.caption("Categories: " + "; ".join(
            category_labels.get(category_id, category_id)
            for category_id in entry["category_ids"]
        ))
    for heading, field in (("Morphology", "morphology"),
                           ("Etymology", "etymology"),
                           ("Notes & usage", "notes")):
        content = entry[field].strip()
        if content:
            st.markdown("#### " + heading)
            st.markdown(content)

def render_dictionary(snapshot, language):
    requested = st.session_state.pop("requested_entry_id", None)
    if requested:
        st.session_state.open_entry = requested
    st.title("Dictionary")
    st.caption("Every word is stored once. Word class and subject categories are independent filters.")
    entries = [x for x in snapshot["entries"] if x["language_id"] == language["id"]]
    classes = snapshot["word_classes"]
    class_labels = {x["id"]:x["name"] for x in classes}
    categories = snapshot["categories"]
    category_names = db.category_path_map(categories)
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        class_ids = ["all"] + [x["id"] for x in classes]
        if st.session_state.get("dict_class") not in class_ids:
            st.session_state.dict_class = "all"
        chosen_class = st.selectbox("Word class", class_ids,
                                    format_func=lambda x:"All word classes" if x=="all" else class_labels[x], key="dict_class")
    with col2:
        chosen_category = category_selector(categories,"dict_category",allow_all=True)
    with col3:
        status = st.selectbox("Status", ["all","draft","established","obsolete"],
                             format_func=lambda x:x.capitalize() if x!="all" else "All statuses")
    search = st.text_input("Search dictionary", placeholder="Word, gloss, meaning, etymology...",key="dict_query")
    if chosen_class != "all":
        entries = [x for x in entries if x["word_class_id"] == chosen_class]
    if chosen_category != "all":
        target_ids = category_descendants(chosen_category,categories)
        entries = [x for x in entries if target_ids.intersection(x["category_ids"])]
    if status != "all":
        entries = [x for x in entries if x["status"] == status]
    if search.strip():
        term = search.casefold().strip()
        entries = [x for x in entries if term in " ".join([x["lemma"],x["gloss"],x["definition"],x["ipa"],x["morphology"],x["etymology"],x["notes"]]).casefold()]
    st.caption(f"{len(entries)} matching entries")
    if entries:
        visible = [{"Lemma":x["lemma"], "Meaning":x["gloss"],
                    "Class":class_labels.get(x["word_class_id"],""),
                    "Categories":", ".join(category_names.get(cat,cat).split(" › ")[-1]
                                           for cat in x["category_ids"])}
                   for x in entries[:5000]]
        if any(x["status"] != "established" for x in entries[:5000]):
            for row, record in zip(visible, entries[:5000]):
                row["Status"] = (record["status"].capitalize()
                                 if record["status"] != "established" else "")
        st.dataframe(visible, use_container_width=True, hide_index=True, height=min(340,70+len(visible)*36))
        if len(entries)>5000:
            st.info("Displaying the first 5,000 matching entries. Narrow your search for more.")
        options = [x["id"] for x in entries]
        if st.session_state.get("open_entry") not in options:
            st.session_state.open_entry = options[0]
        chosen_id = st.selectbox("Open dictionary entry", options,
                                  format_func=lambda x: next(a["lemma"]+" — "+(a["gloss"] or "no gloss") for a in entries if a["id"]==x),
                                  key="open_entry")
        selected = next(x for x in entries if x["id"]==chosen_id)
        read_tab, edit_tab = st.tabs(["📖 Read entry", "✏️ Edit entry"])
        with read_tab:
            with st.container(border=True):
                render_entry_readonly(selected,
                                      class_labels.get(selected["word_class_id"], "Unclassified"),
                                      category_names)
        with edit_tab:
            with st.form("edit_entry_"+chosen_id):
                a,b = st.columns(2)
                with a:
                    lemma = st.text_input("Lemma / dictionary form", value=selected["lemma"])
                    gloss = st.text_input("Short gloss / translation", value=selected["gloss"])
                    ipa = st.text_input("Pronunciation (IPA)", value=selected["ipa"])
                    selected_class = st.selectbox("Word class", [x["id"] for x in classes],
                                                 index=next(i for i,x in enumerate(classes) if x["id"]==selected["word_class_id"]),
                                                 format_func=lambda x:class_labels[x])
                with b:
                    selected_status = st.selectbox("Status", ["draft","established","obsolete"],
                                                   index=["draft","established","obsolete"].index(selected["status"]))
                    selected_cats = st.multiselect("Semantic categories", list(category_names),
                                                    default=selected["category_ids"],
                                                    format_func=lambda x:category_names[x])
                definition = st.text_area("Detailed definition", value=selected["definition"],height=100)
                morphology = st.text_area("Inflection / morphology",value=selected["morphology"],height=90)
                etymology = st.text_area("Etymology",value=selected["etymology"],height=90)
                notes = st.text_area("Notes / usage examples",value=selected["notes"],height=90)
                st.caption("Stable record ID: " + selected["id"])
                if st.form_submit_button("Save changes", type="primary"):
                    if not lemma.strip():
                        st.warning("A lemma is required.")
                    elif save("entries", {"lemma":lemma.strip(),"gloss":gloss,"ipa":ipa,
                                                "word_class_id":selected_class,"status":selected_status,
                                                "category_ids":selected_cats,"definition":definition,
                                                "morphology":morphology,"etymology":etymology,"notes":notes}, chosen_id):
                        st.rerun()
    else:
        st.info("No entries match these filters. You can create one below or import entries from ChatGPT.")
    st.divider()
    with st.expander("+ Add a word manually"):
        with st.form("add_entry",clear_on_submit=True):
            a,b = st.columns(2)
            with a:
                lemma = st.text_input("Lemma *")
                gloss = st.text_input("Short gloss / translation")
                ipa = st.text_input("IPA")
                word_class = st.selectbox("Word class",[x["id"] for x in classes],
                                          format_func=lambda x:class_labels[x],key="add_entry_class")
            with b:
                selected_cats = st.multiselect("Semantic categories", list(category_names),
                                                format_func=lambda x:category_names[x],key="add_entry_categories")
                entry_status = st.selectbox("Status", ["draft","established","obsolete"])
            definition = st.text_area("Detailed definition")
            morphology = st.text_area("Morphology")
            etymology = st.text_area("Etymology")
            notes = st.text_area("Usage notes")
            if st.form_submit_button("Add word",type="primary"):
                if not lemma.strip():
                    st.warning("A lemma is required.")
                else:
                    ident = save("entries", {"language_id":language["id"],"lemma":lemma.strip(),
                             "gloss":gloss,"ipa":ipa,"word_class_id":word_class,
                             "category_ids":selected_cats,"status":entry_status,
                             "definition":definition,"morphology":morphology,
                             "etymology":etymology,"notes":notes})
                    if ident:
                        st.session_state.requested_entry_id = ident
                        st.rerun()


def category_lineage(category_id, categories):
    """Return the ancestor chain, root first. Tolerates a stale/deleted category."""
    by_id = {cat["id"]: cat for cat in categories}
    trail = []
    visited = set()
    ident = category_id
    while ident in by_id and ident not in visited:
        visited.add(ident)
        current = by_id[ident]
        trail.append(current)
        ident = current["parent_id"]
    trail.reverse()
    return trail


def category_entry_count(entries, category_id, categories):
    """Count distinct entries in this category or any nested category."""
    subtree = category_descendants(category_id, categories)
    return sum(bool(subtree.intersection(e["category_ids"])) for e in entries)


def category_navigation(word_class_id=None, category_id=None):
    """Navigate the category browser without changing any dictionary filters."""
    st.session_state.page = "Categories"
    st.session_state.categories_class_id = word_class_id
    st.session_state.categories_node_id = category_id
    st.session_state.pop("category_open_entry", None)
    st.rerun()


def render_category_cards(categories, entries, all_categories, key_prefix):
    """Render direct child categories, ordered according to their stored order."""
    if not categories:
        return
    ordered = sorted(categories, key=lambda c: (c["sort_order"], c["name"].casefold()))
    for start in range(0, len(ordered), 3):
        columns = st.columns(3)
        for col, category in zip(columns, ordered[start:start + 3]):
            count = category_entry_count(entries, category["id"], all_categories)
            with col:
                with st.container(border=True):
                    st.markdown("#### " + category["name"])
                    st.caption(f"{count} {'word' if count == 1 else 'words'} · includes subcategories")
                    if st.button("Browse category →", key=f"{key_prefix}_{category['id']}", use_container_width=True):
                        category_navigation(st.session_state.get("categories_class_id"), category["id"])


def render_category_words(entries, classes, labels, category_id, categories):
    """Show unique vocabulary records and a full reading panel inside the category."""
    if category_id == "__uncategorized__":
        shown = [entry for entry in entries if not entry["category_ids"]]
    elif category_id in (None, "__all__"):
        shown = list(entries)
    else:
        subtree = category_descendants(category_id, categories)
        shown = [entry for entry in entries if subtree.intersection(entry["category_ids"])]

    st.subheader("Vocabulary")
    search_col, status_col = st.columns([3, 1])
    with search_col:
        search = st.text_input("Search words in this section", placeholder="Word, meaning, etymology…",
                               key="category_words_search")
    with status_col:
        status = st.selectbox("Status", ["all", "established", "draft", "obsolete"],
                              format_func=lambda x: "All statuses" if x == "all" else x.capitalize(),
                              key="category_words_status")
    if status != "all":
        shown = [entry for entry in shown if entry["status"] == status]
    if search.strip():
        term = search.casefold().strip()
        shown = [entry for entry in shown if term in " ".join([
            entry["lemma"], entry["gloss"], entry["definition"], entry["ipa"],
            entry["morphology"], entry["etymology"], entry["notes"]
        ]).casefold()]
    shown.sort(key=lambda e: (e["lemma"].casefold(), e["id"]))
    st.caption(f"{len(shown)} matching {'word' if len(shown) == 1 else 'words'}")
    if not shown:
        st.info("No vocabulary entries match this selection.")
        return

    class_labels = {x["id"]: x["name"] for x in classes}
    rows = [{"Word": e["lemma"], "Meaning": e["gloss"],
             "Word class": class_labels.get(e["word_class_id"], "Unclassified")}
            for e in shown[:5000]]
    if any(e["status"] != "established" for e in shown[:5000]):
        for row, record in zip(rows, shown[:5000]):
            row["Status"] = (record["status"].capitalize()
                             if record["status"] != "established" else "")
    st.dataframe(rows, use_container_width=True, hide_index=True,
                 height=min(380, 70 + len(rows) * 36))
    if len(shown) > 5000:
        st.caption("Showing the first 5,000 entries. Use search to narrow the list.")
    choices = [e["id"] for e in shown]
    if st.session_state.get("category_open_entry") not in choices:
        st.session_state.category_open_entry = choices[0]
    chosen_id = st.selectbox("Read a dictionary entry", choices,
                             format_func=lambda ident: next(
                                 e["lemma"] + " — " + (e["gloss"] or "No gloss")
                                 for e in shown if e["id"] == ident),
                             key="category_open_entry")
    selected = next(e for e in shown if e["id"] == chosen_id)
    with st.container(border=True):
        render_entry_readonly(selected,
                              class_labels.get(selected["word_class_id"], "Unclassified"),
                              labels)
        if st.button("Open in Dictionary / Edit entry", key="category_edit_" + chosen_id):
            st.session_state.requested_entry_id = chosen_id
            go("Dictionary", word_class=selected["word_class_id"], category="all", query="")


def render_category_manager(categories, labels):
    """Keep maintenance tools tucked away from the reading experience."""
    with st.expander("⚙ Manage categories (add, rename or move)", expanded=False):
        st.caption("Categories are shared across languages; changes here affect their navigation, not the words themselves.")
        left, right = st.columns(2)
        with left:
            st.markdown("**Add category**")
            with st.form("add_category"):
                name = st.text_input("Name")
                parent_choices = [None] + [x["id"] for x in categories]
                parent = st.selectbox("Parent category", parent_choices,
                                      format_func=lambda x: "Top-level category" if x is None else labels[x])
                if st.form_submit_button("Create category", type="primary"):
                    if not name.strip():
                        st.warning("Name is required.")
                    elif save("categories", {"name": name.strip(), "parent_id": parent,
                                                  "sort_order": len(categories)}):
                        st.rerun()
        with right:
            st.markdown("**Edit category**")
            if categories:
                with st.form("edit_category"):
                    chosen_id = st.selectbox("Category", list(labels), format_func=lambda x: labels[x])
                    chosen = next(x for x in categories if x["id"] == chosen_id)
                    changed_name = st.text_input("Rename", value=chosen["name"])
                    parent_choices = [None] + [x["id"] for x in categories if x["id"] != chosen_id]
                    idx = parent_choices.index(chosen["parent_id"]) if chosen["parent_id"] in parent_choices else 0
                    new_parent = st.selectbox("Move beneath", parent_choices, index=idx,
                                              format_func=lambda x: "Top-level category" if x is None else labels[x])
                    if st.form_submit_button("Save category"):
                        if not changed_name.strip():
                            st.warning("Name is required.")
                        elif not db.can_set_parent(chosen_id, new_parent, categories):
                            st.error("A category cannot be placed beneath one of its descendants.")
                        elif save("categories", {"name": changed_name.strip(), "parent_id": new_parent}, chosen_id):
                            st.rerun()


def render_categories(snapshot, language):
    """Word-class landing pages -> semantic category pages -> vocabulary records."""
    st.title("Categories")
    st.caption("Browse the dictionary by word class and subject. Every word exists only once in the database.")
    categories = snapshot["categories"]
    labels = db.category_path_map(categories)
    classes = sorted(snapshot["word_classes"], key=lambda c: (c["sort_order"], c["name"].casefold()))
    class_by_id = {c["id"]: c for c in classes}
    category_by_id = {c["id"]: c for c in categories}
    language_entries = [e for e in snapshot["entries"] if e["language_id"] == language["id"]]

    class_id = st.session_state.get("categories_class_id")
    category_id = st.session_state.get("categories_node_id")
    if class_id not in class_by_id:
        class_id = None
        st.session_state.categories_class_id = None
    if category_id not in category_by_id and category_id not in (None, "__all__", "__uncategorized__"):
        category_id = None
        st.session_state.categories_node_id = None
    if class_id is None and category_id in ("__all__", "__uncategorized__"):
        category_id = None
        st.session_state.categories_node_id = None
    entries = ([e for e in language_entries if e["word_class_id"] == class_id]
               if class_id else language_entries)

    # The landing page is intentionally distinct from the old list of every category.
    if class_id is None and category_id is None:
        st.subheader("Word Classes")
        st.caption("Choose a class to see its subject categories and vocabulary.")
        for start in range(0, len(classes), 3):
            cols = st.columns(3)
            for col, word_class in zip(cols, classes[start:start + 3]):
                count = sum(e["word_class_id"] == word_class["id"] for e in language_entries)
                with col:
                    with st.container(border=True):
                        st.markdown("#### " + word_class["name"])
                        st.caption(f"{count} {'word' if count == 1 else 'words'}")
                        if st.button("Browse →", key="category_class_" + word_class["id"], use_container_width=True):
                            category_navigation(word_class["id"])
        search = st.text_input("Quick search across subjects or words", key="category_global_search",
                               placeholder="e.g. weapons, geography, Rôs…")
        if search.strip():
            term = search.casefold().strip()
            matching_categories = [c for c in categories if term in labels[c["id"]].casefold()]
            matching_entries = [e for e in language_entries if term in " ".join([
                e["lemma"], e["gloss"], e["definition"], e["notes"]]).casefold()]
            if matching_categories:
                st.markdown("**Matching subject categories**")
                for cat in matching_categories[:15]:
                    if st.button(labels[cat["id"]] + " →", key="cat_search_" + cat["id"]):
                        category_navigation(None, cat["id"])
            if matching_entries:
                st.markdown("**Matching dictionary entries**")
                for e in matching_entries[:15]:
                    if st.button(e["lemma"] + " — " + (e["gloss"] or "No gloss"), key="entry_search_" + e["id"]):
                        st.session_state.requested_entry_id = e["id"]
                        go("Dictionary", word_class=e["word_class_id"], category="all", query="")
            if not matching_categories and not matching_entries:
                st.info("No matching subjects or words.")
        st.divider()
        render_category_manager(categories, labels)
        return

    # Breadcrumb buttons act as navigation, even for deeply nested categories.
    breadcrumbs = st.columns([2, 2, 2, 2, 2])
    with breadcrumbs[0]:
        if st.button("‹ All classes", use_container_width=True, key="cat_breadcrumb_root"):
            category_navigation()
    if class_id:
        with breadcrumbs[1]:
            if st.button("‹ " + class_by_id[class_id]["name"], key="cat_breadcrumb_class", use_container_width=True):
                category_navigation(class_id)

    if category_id in (None, "__all__", "__uncategorized__"):
        title = class_by_id[class_id]["name"] if class_id else "All classes"
        if category_id == "__all__":
            st.header("All " + title.lower())
        elif category_id == "__uncategorized__":
            st.header(title + " · Uncategorized")
        else:
            st.header(title)
        if category_id is None:
            st.caption("Select a subject to explore its subdivisions. Counts include words within nested subjects.")
            roots = [c for c in categories if c["parent_id"] is None]
            show_empty = st.checkbox("Show empty categories", key="show_empty_root")
            visible = roots if show_empty else [c for c in roots if category_entry_count(entries, c["id"], categories)]
            if visible:
                render_category_cards(visible, entries, categories, "category_root_card")
            else:
                st.info("No categorized words yet. You can show empty categories or add a word in Dictionary.")
            st.divider()
            a, b = st.columns(2)
            with a:
                if st.button(f"Browse all {title.lower()} ({len(entries)})", use_container_width=True):
                    category_navigation(class_id, "__all__")
            uncategorized = sum(not e["category_ids"] for e in entries)
            with b:
                if st.button(f"Uncategorized ({uncategorized})", use_container_width=True):
                    category_navigation(class_id, "__uncategorized__")
        else:
            render_category_words(entries, classes, labels, category_id, categories)
    else:
        chain = category_lineage(category_id, categories)
        category = category_by_id[category_id]
        st.header(category["name"])
        st.caption(" › ".join(c["name"] for c in chain))
        # Every ancestor is a clickable breadcrumb, including deep nesting.
        ancestors = chain[:-1]
        for start in range(0, len(ancestors), 4):
            row = st.columns(len(ancestors[start:start + 4]))
            for col, ancestor in zip(row, ancestors[start:start + 4]):
                with col:
                    if st.button("‹ " + ancestor["name"],
                                 key="cat_ancestor_" + ancestor["id"], use_container_width=True):
                        category_navigation(class_id, ancestor["id"])
        children = [c for c in categories if c["parent_id"] == category_id]
        if children:
            st.subheader("Subcategories")
            show_empty = st.checkbox("Show empty subcategories", key="show_empty_subcategory")
            visible = children if show_empty else [c for c in children if category_entry_count(entries, c["id"], categories)]
            if visible:
                render_category_cards(visible, entries, categories, "category_child_card")
            else:
                st.caption("No subcategories have words yet. Enable 'Show empty subcategories' to browse them.")
        st.divider()
        render_category_words(entries, classes, labels, category_id, categories)

    st.divider()
    render_category_manager(categories, labels)


def render_languages(snapshot, language):
    st.title("Languages")
    st.caption("Each language has its own dictionary and foundational articles. Categories are shared.")
    for item in snapshot["languages"]:
        with st.container(border=True):
            a,b = st.columns([4,1])
            with a:
                st.markdown(f"**{item['name']}** · {item['stage'] or 'Stage not specified'}")
                st.caption(item["description"] or "No description")
            with b:
                if st.button("Open",key="select_lang_"+item["id"]):
                    st.session_state.requested_language_id = item["id"]
                    go("Home")
    st.subheader("Edit current language")
    with st.form("edit_language"):
        name = st.text_input("Name",value=language["name"])
        stage = st.text_input("Historical stage / period",value=language["stage"])
        description = st.text_area("Description",value=language["description"])
        if st.form_submit_button("Save language"):
            if not name.strip():
                st.warning("A name is required.")
            elif save("languages",{"name":name.strip(),"stage":stage,"description":description},language["id"]):
                st.rerun()
    with st.expander("+ Add a language"):
        with st.form("new_language"):
            name = st.text_input("Language name")
            stage = st.text_input("Historical stage / period")
            description = st.text_area("Description")
            if st.form_submit_button("Add language"):
                if not name.strip():
                    st.warning("Language name is required.")
                else:
                    try:
                        language_id = db.save_record("languages",{"name":name.strip(),"stage":stage,"description":description})
                        with db.connect() as conn:
                            db.ensure_foundations(conn,language_id)
                        st.session_state.requested_language_id = language_id
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))


def render_exchange(snapshot):
    st.title("Import / Export")
    st.caption("Exchange text-only JSON files with ChatGPT. No API, internet access, or subscription is needed for this local app.")
    rev = snapshot["revision"]
    st.info(f"Current revision: **{rev}**. AI-generated patches must specify this exact `base_revision`.")
    a,b = st.columns(2)
    with a:
        with st.container(border=True):
            st.subheader("1. Export archive")
            st.write("Download every language, foundation article, word class, category, and dictionary entry in a structured JSON file.")
            data = json.dumps(snapshot,ensure_ascii=False,indent=2)
            st.download_button("Download full JSON snapshot",data=data,
                               file_name=f"vuntric-archive-revision-{rev}.json",mime="application/json",
                               use_container_width=True,type="primary")
    with b:
        with st.container(border=True):
            st.subheader("2. Get an update template")
            st.write("A minimal patch file containing the correct revision and structure. Changes can be generated by ChatGPT.")
            template = json.dumps(db.make_patch_template(),ensure_ascii=False,indent=2)
            st.download_button("Download empty update template",data=template,
                               file_name=f"vuntric-patch-template-revision-{rev}.json",mime="application/json",
                               use_container_width=True)
    with st.expander("Instructions for ChatGPT",expanded=True):
        st.code("""Read my attached Vûntric Linguistic Archive snapshot. We will discuss changes.
After we agree on changes, create a downloadable UTF-8 JSON file with:
  format: 'vuntric-archive'
  schema_version: 1
  kind: 'patch'
  base_revision: <the snapshot's revision>
  changes: [ ... ]
Every operation has op ('add', 'update', or 'delete'), collection
('entries', 'foundations', 'categories', 'languages', 'word_classes'),
plus data for add/update or id for update/delete.
Use stable IDs from my snapshot for updates. Use category_ids for word categories.
Preserve all decisions already in the archive; don't invent canon.
Make the file importable and provide a download link.""",language="text")
        st.caption("Tip: Keep the snapshot attached during a discussion. Do not edit the local database between export and importing the finished patch, or the revision check will reject it.")
    st.divider()
    st.subheader("3. Import updates or restore a snapshot")
    st.write("Upload the generated patch file to merge its changes, or upload a full snapshot to restore the database to that saved state.")
    upload = st.file_uploader("Choose JSON file",type=["json"],accept_multiple_files=False)
    if upload:
        try:
            doc = json.loads(upload.getvalue().decode("utf-8-sig"))
            summary = db.preview_import(doc)
        except Exception as exc:
            st.error(f"Import rejected during validation: {exc}")
        else:
            st.success("Validation passed. No data has been changed yet.")
            if summary["kind"]=="patch":
                a,b,c = st.columns(3)
                a.metric("New records",summary["add"])
                b.metric("Updated records",summary["update"])
                c.metric("Deletions",summary["delete"])
                with st.expander("Preview the first 30 operations"):
                    st.json(doc["changes"][:30])
                if summary["total"]==0:
                    st.info("This update package has no changes.")
            else:
                st.warning("A full snapshot **replaces** the current database, including changes made since that snapshot. A backup will be created first.")
                st.write(f"Snapshot contains {summary['languages']} languages, {summary['foundations']} articles, {summary['categories']} categories and {summary['entries']} dictionary entries.")
            confirmed = st.checkbox("I have reviewed these changes and authorize the import",key="confirm_import")
            if st.button("Apply import to local database",type="primary",disabled=not confirmed or (summary["kind"]=="patch" and summary["total"]==0)):
                try:
                    _, backup = db.execute_import(doc)
                except Exception as exc:
                    st.error(f"Import failed; no changes were committed. Error: {exc}")
                else:
                    st.success(f"Import complete. An automatic backup was saved as {backup.name}.")
                    st.caption("Remove the uploaded file or refresh the page to view updated data.")
    st.divider()
    st.subheader("Backup location")
    st.code(str(db.BACKUP_DIR),language="text")
    st.caption("An SQLite backup is created automatically before every successful import. To keep copies elsewhere, download full JSON snapshots regularly or copy the entire data/ directory.")


snapshot = counts_snapshot()
requested_lang = st.session_state.pop("requested_language_id", None)
if requested_lang:
    st.session_state.language_id = requested_lang
sidebar(snapshot["languages"])
language = next(x for x in snapshot["languages"] if x["id"]==st.session_state.language_id)
page = st.session_state.page
if page == "Home":
    render_home(snapshot,language)
elif page == "Language Foundations":
    render_foundations(snapshot,language)
elif page == "Dictionary":
    render_dictionary(snapshot,language)
elif page == "Categories":
    render_categories(snapshot,language)
elif page == "Languages":
    render_languages(snapshot,language)
elif page == "Import / Export":
    render_exchange(snapshot)