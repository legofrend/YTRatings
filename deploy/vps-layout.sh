#!/usr/bin/env bash
# Prepare / migrate VPS project layout without stopping YTR.
#
# Target:
#   /srv/projects/ytratings   → YTRatings monorepo (canonical)
#   /srv/projects/endup|…     → former /root/oleg/*
#   /var/www/o2t4/…           → keep working via reverse symlink until configs updated
#
# Usage (on VPS as root):
#   bash deploy/vps-layout.sh prepare   # safe now: mkdir + forward symlink, move oleg
#   bash deploy/vps-layout.sh cutover   # mv YTR + reverse symlink (no docker stop)
#   bash deploy/vps-layout.sh status
#   bash deploy/vps-layout.sh retarget  # rewrite nginx/systemd to /srv/projects/… + reload
#
# Why YTR can move while running:
#   - docker: named volume for Postgres; app has no host bind-mount of the repo
#   - nginx/systemd: keep resolving via reverse symlink at the OLD path
#   - next `docker compose up --build` / deploy can use either path until retarget
set -euo pipefail

PROJECTS_ROOT="${PROJECTS_ROOT:-/srv/projects}"
YTR_OLD="${YTR_OLD:-/var/www/o2t4/backend/YTRatings}"
YTR_NEW="${YTR_NEW:-$PROJECTS_ROOT/ytratings}"
OLEG_ROOT="${OLEG_ROOT:-/root/oleg}"

die() { echo "ERROR: $*" >&2; exit 1; }
step() { printf '\n=== %s ===\n' "$1"; }
info() { printf '  %s\n' "$*"; }

need_root() {
  [[ "$(id -u)" -eq 0 ]] || die "run as root on VPS"
}

status() {
  step "layout status"
  info "PROJECTS_ROOT=$PROJECTS_ROOT"
  ls -la "$PROJECTS_ROOT" 2>/dev/null || info "(missing)"
  echo
  if [[ -L "$YTR_NEW" ]]; then
    info "ytratings: symlink → $(readlink -f "$YTR_NEW" 2>/dev/null || readlink "$YTR_NEW")"
  elif [[ -d "$YTR_NEW" ]]; then
    info "ytratings: real dir at $YTR_NEW"
  else
    info "ytratings: absent"
  fi
  if [[ -L "$YTR_OLD" ]]; then
    info "old path: symlink → $(readlink -f "$YTR_OLD" 2>/dev/null || readlink "$YTR_OLD")"
  elif [[ -d "$YTR_OLD" ]]; then
    info "old path: real dir at $YTR_OLD"
  else
    info "old path: absent"
  fi
  echo
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || true
  systemctl is-active ytr-auto.timer 2>/dev/null | awk '{print "ytr-auto.timer: "$0}' || true
  curl -sS -o /dev/null -w "ytr.o2t4.ru HTTP %{http_code}\n" --max-time 5 https://ytr.o2t4.ru/ || true
}

# Phase 1 — zero risk for YTR: create tree, alias new name → current location, park oleg.
prepare() {
  need_root
  step "prepare $PROJECTS_ROOT (YTR stays put)"
  mkdir -p "$PROJECTS_ROOT" /var/www/o2t4/backend

  if [[ -e "$YTR_NEW" ]]; then
    info "skip: $YTR_NEW already exists"
  else
    [[ -d "$YTR_OLD" ]] || die "YTR not found at $YTR_OLD"
    ln -s "$YTR_OLD" "$YTR_NEW"
    info "linked $YTR_NEW → $YTR_OLD"
  fi

    # Flat list under /srv/projects (no "oleg" layer). nginx endup uses ~/oleg/end-up/...
  # → /root/oleg becomes a symlink to /srv/projects so old paths keep working.
  step "flatten projects into $PROJECTS_ROOT (no oleg/ wrapper)"
  flatten_from=""
  if [[ -L "$OLEG_ROOT" ]]; then
    target="$(readlink -f "$OLEG_ROOT" 2>/dev/null || readlink "$OLEG_ROOT")"
    if [[ "$target" == "$PROJECTS_ROOT/oleg" && -d "$PROJECTS_ROOT/oleg" ]]; then
      flatten_from="$PROJECTS_ROOT/oleg"
    elif [[ "$target" == "$PROJECTS_ROOT" ]]; then
      info "skip: $OLEG_ROOT already → $PROJECTS_ROOT"
    else
      info "skip oleg symlink → $target (unexpected; fix manually)"
    fi
  elif [[ -d "$OLEG_ROOT" ]]; then
    flatten_from="$OLEG_ROOT"
  elif [[ -d "$PROJECTS_ROOT/oleg" ]]; then
    flatten_from="$PROJECTS_ROOT/oleg"
  else
    info "no oleg tree — skip flatten"
  fi

  if [[ -n "$flatten_from" ]]; then
    shopt -s nullglob
    for src in "$flatten_from"/*; do
      base="$(basename "$src")"
      dest="$PROJECTS_ROOT/$base"
      if [[ -e "$dest" || -L "$dest" ]]; then
        # drop stale convenience symlinks into oleg/
        if [[ -L "$dest" && "$(readlink "$dest")" == *"/oleg/"* ]]; then
          rm -f "$dest"
        else
          info "skip exists: $dest (left $src)"
          continue
        fi
      fi
      mv "$src" "$dest"
      info "moved $src → $dest"
    done
    shopt -u nullglob
    # leftover: .git / dotfiles of the old umbrella repo
    if [[ -d "$flatten_from" ]]; then
      leftover="$PROJECTS_ROOT/_oleg-umbrella-leftover"
      if [[ -e "$leftover" ]]; then
        info "left non-empty $flatten_from (resolve manually)"
      else
        mv "$flatten_from" "$leftover"
        info "umbrella leftovers → $leftover (safe to delete later)"
      fi
    fi
  fi

  # remove old convenience aliases if still pointing into oleg
  for alias in endup simplelms telegram-bot; do
    p="$PROJECTS_ROOT/$alias"
    [[ -L "$p" && "$(readlink "$p")" == *"/oleg/"* ]] && rm -f "$p" && info "removed stale alias $p"
  done

  # compat: ~/oleg/<project> → /srv/projects/<project>
  if [[ -L "$OLEG_ROOT" ]]; then
    current="$(readlink -f "$OLEG_ROOT" 2>/dev/null || true)"
    if [[ "$current" != "$PROJECTS_ROOT" ]]; then
      rm -f "$OLEG_ROOT"
      ln -s "$PROJECTS_ROOT" "$OLEG_ROOT"
      info "compat: $OLEG_ROOT → $PROJECTS_ROOT"
    fi
  elif [[ ! -e "$OLEG_ROOT" ]]; then
    ln -s "$PROJECTS_ROOT" "$OLEG_ROOT"
    info "compat: $OLEG_ROOT → $PROJECTS_ROOT"
  else
    info "WARN: $OLEG_ROOT is a real dir — leave as-is"
  fi

  step "done prepare"
  info "canonical alias: $YTR_NEW → live tree (containers untouched)"
  info "next when ready: bash deploy/vps-layout.sh cutover"
  status
}

# Phase 2 — physical move; keep OLD path as symlink so nginx/systemd/deploy keep working.
# No docker stop. Brief window between mv and ln is milliseconds (same script).
cutover() {
  need_root
  step "cutover YTR → $YTR_NEW (no docker stop)"

  if [[ -d "$YTR_NEW" && ! -L "$YTR_NEW" ]]; then
    info "already cut over (real dir at $YTR_NEW)"
    if [[ ! -e "$YTR_OLD" ]]; then
      mkdir -p "$(dirname "$YTR_OLD")"
      ln -s "$YTR_NEW" "$YTR_OLD"
      info "restored reverse symlink $YTR_OLD → $YTR_NEW"
    fi
    status
    return 0
  fi

  [[ -d "$YTR_OLD" && ! -L "$YTR_OLD" ]] || die "expected real dir at $YTR_OLD (run prepare first?)"

  # Drop forward symlink if prepare made it
  if [[ -L "$YTR_NEW" ]]; then
    rm -f "$YTR_NEW"
  fi
  [[ ! -e "$YTR_NEW" ]] || die "$YTR_NEW exists and is not a removable symlink"

  # Atomic-enough: move then immediately reverse-link old path
  mv "$YTR_OLD" "$YTR_NEW"
  ln -s "$YTR_NEW" "$YTR_OLD"

  info "moved → $YTR_NEW"
  info "compat: $YTR_OLD → $YTR_NEW"
  info "docker/nginx still use old paths via symlink — no restart required"
  info "optional later: bash deploy/vps-layout.sh retarget"

  # smoke
  [[ -d "$YTR_NEW/site" ]] || info "WARN: site/ missing under new path"
  [[ -d "$YTR_NEW/media" ]] || info "WARN: media/ missing under new path"
  curl -sS -o /dev/null -w "smoke ytr HTTP %{http_code}\n" --max-time 5 https://ytr.o2t4.ru/ || true
  curl -sS -o /dev/null -w "smoke api HTTP %{http_code}\n" --max-time 5 https://ytr.o2t4.ru/api/ytr/v2/ || true
  status
}

# Phase 3 — point nginx + systemd at canonical path; reload (no container recreate).
retarget() {
  need_root
  [[ -d "$YTR_NEW" && ! -L "$YTR_NEW" ]] || die "cutover first (real dir at $YTR_NEW)"

  step "retarget nginx + systemd → $YTR_NEW"
  NGINX_SRC="$YTR_NEW/deploy/nginx/ytr.nginx.conf"
  [[ -f "$NGINX_SRC" ]] || die "missing $NGINX_SRC"

  # Rewrite paths in a temp conf then install
  tmp="$(mktemp)"
  sed -e "s|/var/www/o2t4/backend/YTRatings|$YTR_NEW|g" "$NGINX_SRC" >"$tmp"
  # landing o2t4.ru root stays /var/www/o2t4/ — sed above only hits YTRatings paths
  cp "$tmp" /etc/nginx/sites-available/ytr
  rm -f "$tmp"
  nginx -t
  systemctl reload nginx
  info "nginx reloaded"

  sed -e "s|/var/www/o2t4/backend/YTRatings|$YTR_NEW|g" \
    "$YTR_NEW/deploy/systemd/ytr-auto.service" >/etc/systemd/system/ytr-auto.service
  cp "$YTR_NEW/deploy/systemd/ytr-auto.timer" /etc/systemd/system/ytr-auto.timer
  systemctl daemon-reload
  systemctl restart ytr-auto.timer
  info "systemd retargeted (timer restarted — oneshot jobs unaffected)"

  step "retarget done"
  info "update local deploy REMOTE_ROOT default to $YTR_NEW when convenient"
  info "compat symlink $YTR_OLD can stay forever or be removed after deploy scripts updated"
  status
}

cmd="${1:-status}"
case "$cmd" in
  prepare|cutover|retarget|status) "$cmd" ;;
  *) die "usage: $0 {prepare|cutover|retarget|status}" ;;
esac
