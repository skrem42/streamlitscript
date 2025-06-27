import streamlit as st
from apify_client import ApifyClient
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("APIFY_API_KEY")
client = ApifyClient(API_KEY)

st.set_page_config(layout="wide")
st.title("Instagram Similar Accounts Finder")

# — Persisted state for hidden rows —
if "hidden" not in st.session_state:
    st.session_state.hidden = []

# — Inputs —
ig_input = st.text_input("Enter Instagram URL or @username")
def hide_user(username):
    st.session_state.hidden.append(username)

def unhide_all():
    st.session_state.hidden = []
# — Fetch on button click —
if st.button("Find Profiles"):
    username = (
        ig_input.strip()
        .replace("https://www.instagram.com/", "")
        .replace("@", "")
        .strip("/")
    )
    # reset cache if new
    if st.session_state.get("fetched") != username:
        st.session_state.fetched = username
        st.session_state.enriched = None
        st.session_state.hidden = []

    with st.spinner("📡 Fetching related profiles…"):
        # 1) Fetch main + suggestions
        run1 = client.actor("apify/instagram-profile-scraper").call(run_input={
            "usernames":         [username],
            "scrapeSuggestions": True,
            "storePhotos":       True,
            "resultsLimit":      1,
        })
        ds1 = list(client.dataset(run1["defaultDatasetId"]).iterate_items())
        if not ds1 or not ds1[0].get("relatedProfiles"):
            st.warning("⚠️ No related profiles found.")
        else:
            # fetch all related profiles, then limit display in filters
            usernames = [p["username"] for p in ds1[0]["relatedProfiles"]]

            # 2) Batch enrich
            run2 = client.actor("apify/instagram-profile-scraper").call(run_input={
                "usernames":         usernames,
                "scrapeSuggestions": False,
                "storePhotos":       True,
                "resultsLimit":      len(usernames),
            })
            ds2 = list(client.dataset(run2["defaultDatasetId"]).iterate_items())

            enriched = []
            for item in ds2:
                u = item.get("user", item)
                # split fullName into first and surname
                full = u.get("fullName", "").strip()
                parts = full.split()
                first = parts[0] if parts else ""
                last = parts[-1] if len(parts) > 1 else ""
                # find hosted pic
                pic = None
                for att in item.get("attachments", []):
                    if att.get("key") == "profilePic":
                        pic = att.get("url")
                        break
                pic = pic or u.get("profilePicUrlHD") or u.get("profilePicUrl")

                enriched.append({
                    "username":     u.get("username",""),
                    "first_name":   first,
                    "surname":      last,
                    "biography":    u.get("biography",""),
                    "external_url": u.get("externalUrl",""),
                    "followers":    u.get("followersCount", 0),
                    "following":    u.get("followsCount", 0),
                    "private":      u.get("private", u.get("isPrivate", False)),
                    "verified":     u.get("verified", u.get("isVerified", False)),
                    "picture":      pic,
                    "profile_url":  f"https://instagram.com/{u.get('username','')}",
                })

            st.session_state.enriched = enriched

# — Once we have data, show filters, table, download —
if st.session_state.get("enriched"):
    enriched = st.session_state.enriched

    # — Sidebar filters —
    st.sidebar.header("Filter results")
    st.sidebar.button("Unhide All", on_click=unhide_all)
    min_f = min(p["followers"] for p in enriched)
    max_f = max(p["followers"] for p in enriched)
    follower_options = sorted({p["followers"] for p in enriched})
    f_low, f_high = st.sidebar.select_slider(
        "Followers range",
        options=follower_options,
        value=(min_f, max_f),
    )
    private_filter = st.sidebar.selectbox(
        "Private status",
        ("Both", "Private only", "Public only"),
        index=0,
    )
    verified_filter = st.sidebar.selectbox(
        "Verified status",
        ("Both", "Verified only", "Unverified only"),
        index=0,
    )
    firstname_filter = st.sidebar.selectbox(
        "First name status",
        ("Both", "Has first name", "No first name"),
        index=0,
    )
    surname_filter = st.sidebar.selectbox(
        "Surname status",
        ("Both", "Has surname", "No surname"),
        index=0,
    )
    external_filter = st.sidebar.selectbox(
        "External URL",
        ("Both", "With link", "Without link"),
        index=0,
    )
    bio_filter     = st.sidebar.text_input("Biography contains…").strip().lower()
    fn_filter      = st.sidebar.text_input("First name contains…").strip().lower()
    ln_filter      = st.sidebar.text_input("Surname contains…").strip().lower()

    def keep(p):
        if not (f_low <= p["followers"] <= f_high):               return False
        # if show_private   and not p["private"]:                   return False
        # if show_verified  and not p["verified"]:                  return False
        # if show_fn  and not p["first_name"]:                  return False
        # if show_sn  and not p["surname"]:                  return False
        # if only_with_link and not p["external_url"]:              return False
        if private_filter == "Private only" and not p["private"]:
            return False
        if private_filter == "Public only" and p["private"]:
            return False
        if verified_filter == "Verified only" and not p["verified"]:
            return False
        if verified_filter == "Unverified only" and p["verified"]:
            return False
        if firstname_filter == "Has first name" and not p["first_name"]:
            return False
        if firstname_filter == "No first name" and p["first_name"]:
            return False
        if surname_filter == "Has surname" and not p["surname"]:
            return False
        if surname_filter == "No surname" and p["surname"]: 
            return False
        if external_filter == "With link" and not p["external_url"]:
            return False
        if external_filter == "Without link" and p["external_url"]:
            return False
        if bio_filter     and bio_filter     not in p["biography"].lower(): return False
        if fn_filter      and fn_filter      not in p["first_name"].lower(): return False
        if ln_filter      and ln_filter      not in p["surname"].lower():    return False
        return True

    filtered = [p for p in enriched if keep(p)]
    # let user choose how many to display
    max_display = st.sidebar.slider(
        "Max profiles to display", 1, len(filtered), len(filtered)
    )
    visible = [p for p in filtered if p["username"] not in st.session_state.hidden][:max_display]

    st.markdown(f"**{len(visible)}** of **{len(filtered)}** profiles visible; **{len(filtered)-len(visible)}** hidden.")

    # — Download —
    txt = "\n".join(p["username"] for p in visible)
    st.download_button(
        "Download usernames (one per line)",
        txt,
        file_name=f"{st.session_state.fetched}_similar.txt",
        mime="text/plain",
    )

    # — Table headers —
    headers = ["Photo","Username","First Name","Surname","Biography","Followers","Following","Private","Verified","Link","Hide"]
    cols = st.columns([1,2,1,1,3,1,1,1,1,1,1])
    for c,h in zip(cols, headers):
        c.markdown(f"**{h}**")

    # — Rows —
    for p in visible:
        row = st.columns([1,2,1,1,3,1,1,1,1,1,1])
        row[0].image(p["picture"], width=60)
        row[1].markdown(f"[**{p['username']}**]({p['profile_url']})")
        row[2].write(p["first_name"] or "-")
        row[3].write(p["surname"]    or "-")
        row[4].write(p["biography"]  or "-")
        row[5].write(p["followers"])
        row[6].write(p["following"])
        row[7].write("🔒" if p["private"] else "-")
        row[8].write("✔️" if p["verified"] else "-")
        row[9].write(f"[link]({p['external_url']})" if p["external_url"] else "-")
        row[10].button("Hide", key=f"hide_{p['username']}", on_click=hide_user, args=(p["username"],))