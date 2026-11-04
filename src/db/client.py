"""Supabase 클라이언트 싱글턴."""
import streamlit as st
from supabase import Client, create_client

from src.core.config import get_settings


@st.cache_resource
def get_supabase() -> Client:
    s = get_settings()
    if not s.supabase_url or not s.supabase_anon_key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_ANON_KEY 가 설정되지 않았습니다 (.env 확인).")
    return create_client(s.supabase_url, s.supabase_anon_key)
