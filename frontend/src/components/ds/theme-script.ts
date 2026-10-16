// Server-safe (no "use client"): imported by app/layout.tsx for the pre-paint theme script.

export const THEME_STORAGE_KEY = "atelier-theme";

/** Runs in <head> before paint. Keep it tiny and dependency-free. */
export const THEME_SCRIPT = `(function(){try{var d=document.documentElement,k="${THEME_STORAGE_KEY}",q=new URLSearchParams(location.search).get("theme");if(q==="light"||q==="dark"){localStorage.setItem(k,q)}var s=localStorage.getItem(k);var t=s==="light"||s==="dark"?s:(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");d.setAttribute("data-theme",t);d.style.colorScheme=t}catch(e){}})()`;

