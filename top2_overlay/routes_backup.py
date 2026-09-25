from .core import *

# BACKUP
# ==============================
@app.route("/backup")
@login_required
def backup_page():
   existing = sorted(BACKUP_DIR.glob('backup_*.zip'), key=lambda p: p.stat().st_mtime, reverse=True) if BACKUP_DIR.exists() else []
   latest = existing[0].stat().st_mtime if existing else None
   latest_label = datetime.fromtimestamp(latest).strftime('%d/%m/%Y %H:%M') if latest else 'Nessun backup disponibile'
   return layout(f"""
   <div class='app-section-hero'>
       <div class='kicker'>Sicurezza dati</div>
       <h2 class='section-title'>Backup completo</h2>
       <div class='small-muted'>Crea o ripristina un archivio ZIP locale con database, tenant, configurazioni, media, PDF e documenti caricati.</div>
   </div>
   <div class='metric-strip'>
      <div class='metric-box'><div class='label'>Backup presenti</div><div class='value'>{len(existing)}</div></div>
      <div class='metric-box'><div class='label'>Ultimo backup</div><div class='value' style='font-size:1.1rem;line-height:1.2;'>{latest_label}</div></div>
   </div>
   <div class='card form-panel'>
       <div class='kicker'>Operazione guidata</div>
       <h3 class='section-title'>Genera backup completo</h3>
       <p class='small-muted'>Viene creato un file `.zip` scaricabile subito. Include tutto ciò che serve per restore operativo.</p>
       <form method='POST' action='/backup/create'>
           {csrf_input()}
           <button>Crea e scarica backup</button>
       </form><form method='POST' action='/backup/test' style='margin-top:10px'>{csrf_input()}<button type='submit'>Test integrità backup adesso</button></form>
   </div>
   <div class='card form-panel'>
       <div class='kicker'>Restore controllato</div>
       <h3 class='section-title'>Ripristina backup completo</h3>
       <p class='small-muted'>Carica un backup ZIP generato da questa app. Prima del ripristino viene creato automaticamente un backup di sicurezza dello stato attuale.</p>
       <form method='POST' action='/backup/restore' enctype='multipart/form-data' onsubmit="return confirm('Ripristinare questo backup? Verrà creato prima un backup di sicurezza dello stato attuale.');">
           {csrf_input()}
           <input type='file' name='backup_file' accept='.zip' required>
           <button class='warning'>Ripristina backup</button>
       </form>
   </div>
   """)


def _safe_zip_add_file(zip_handle, file_path, arcname, added: set[str] | None = None):
   try:
      file_path = Path(file_path)
      arcname = str(arcname).replace('\\', '/').lstrip('/').replace('..', '_')
      if added is not None and arcname in added:
         return
      if file_path.is_file():
         zip_handle.write(file_path, arcname)
         if added is not None:
            added.add(arcname)
   except Exception as exc:
      try: log_exception(f"backup add file failed {file_path}: {exc}")
      except Exception: pass


def _safe_zip_add_dir(zip_handle, dir_path, arc_prefix, added: set[str] | None = None):
   try:
      dir_path = Path(dir_path)
      if not dir_path.exists() or not dir_path.is_dir():
         return
      for item in dir_path.rglob('*'):
         if item.is_file():
            rel = item.relative_to(dir_path)
            _safe_zip_add_file(zip_handle, item, Path(arc_prefix) / rel, added=added)
   except Exception as exc:
      try: log_exception(f"backup add dir failed {dir_path}: {exc}")
      except Exception: pass


def _create_backup_zip(prefix: str = "backup_completo") -> Path:
   import zipfile
   BACKUP_DIR.mkdir(parents=True, exist_ok=True)
   stamp = now().strftime('%Y%m%d_%H%M%S_%f')
   tmp_db = BACKUP_DIR / f"backup_db_{stamp}.sqlite"
   zip_path = BACKUP_DIR / f"{prefix}_{stamp}.zip"
   current_db_path = get_workspace_db_path(current_tenant_slug()).resolve()
   source_conn = None
   backup_conn = None
   try:
      source_conn = db()
      backup_conn = sqlite3.connect(tmp_db)
      source_conn.backup(backup_conn)
      backup_conn.close(); backup_conn = None
      source_conn.close(); source_conn = None
      added: set[str] = set()
      with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
         for item in DATA_DIR.rglob('*'):
            if not item.is_file():
               continue
            resolved = item.resolve()
            try:
               resolved.relative_to(BACKUP_DIR.resolve())
               continue
            except Exception:
               pass
            if item.name.endswith(('-journal', '-wal', '-shm')):
               continue
            rel = item.relative_to(DATA_DIR)
            if resolved == current_db_path:
               _safe_zip_add_file(zf, tmp_db, rel, added=added)
            else:
               _safe_zip_add_file(zf, item, rel, added=added)
         _safe_zip_add_file(zf, tmp_db, 'database/asd.db', added=added)
      return zip_path
   finally:
      try:
         if backup_conn is not None: backup_conn.close()
      except Exception: pass
      try:
         if source_conn is not None: source_conn.close()
      except Exception: pass
      try: tmp_db.unlink(missing_ok=True)
      except Exception: pass


def _verify_backup_zip(zip_path: Path) -> tuple[bool, str]:
   import zipfile, tempfile
   try:
      with zipfile.ZipFile(zip_path) as zf:
         bad=zf.testzip()
         if bad: return False, f"File corrotto nello ZIP: {bad}"
         names=zf.namelist()
         db_member='database/asd.db' if 'database/asd.db' in names else next((n for n in names if n.endswith('/database/asd.db')), '')
         if not db_member: return False, 'Snapshot database non presente nel backup.'
         with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'verify.sqlite'; target.write_bytes(zf.read(db_member))
            conn=sqlite3.connect(target)
            try:
               chk=conn.execute('PRAGMA integrity_check').fetchone()
               if not chk or str(chk[0]).lower()!='ok': return False, f"SQLite integrity_check: {chk[0] if chk else 'nessun esito'}"
               n=conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            finally: conn.close()
         return True, f"ZIP integro · database SQLite OK · {n} tabelle"
   except Exception as exc:
      return False, str(exc)

@app.route("/backup/create", methods=["POST"])
@login_required
def backup_create():
   try:
       zip_path = _create_backup_zip("backup_completo")
       ok, detail = _verify_backup_zip(zip_path)
       if not ok:
           raise ValueError('Backup creato ma non supera la verifica di integrita: ' + detail)
       cleanup_old_files(BACKUP_DIR, "backup_completo_*.zip", keep=20)
       cleanup_old_files(BACKUP_DIR, "pre_restore_*.zip", keep=10)
       cleanup_old_files(BACKUP_DIR, "backup_*.db", keep=5)
       cleanup_old_files(BACKUP_DIR, "backup_db_*.sqlite", keep=0)
       return send_file(zip_path, as_attachment=True)
   except Exception as exc:
       try: log_exception(f"backup_create: {exc}")
       except Exception: pass
       return layout(alert_html("Errore durante il backup completo.", "error") + details_block("Dettagli", e(str(exc))))


def _is_safe_zip_member(name: str) -> bool:
   normalized = str(name or '').replace('\\', '/').lstrip('/')
   if not normalized or normalized.startswith('../') or '/../' in normalized:
      return False
   if normalized.startswith('backups/'):
      return False
   allowed = ('database/', 'config/', 'tenants/', 'media/', 'pdf/', 'user_static/', 'license.json', '.secret_key', 'logs/')
   return normalized.startswith(allowed)


@app.route("/backup/restore", methods=["POST"])
@login_required
@admin_required
def backup_restore():
   uploaded = request.files.get('backup_file')
   if not uploaded or not uploaded.filename:
      return redirect_with_message('/backup', 'Seleziona un file backup ZIP.', 'error')
   try:
      import zipfile, tempfile, os as _os
      tenant_slug = current_tenant_slug()
      target_db = get_workspace_db_path(tenant_slug).resolve()
      target_cfg = get_workspace_config_path(tenant_slug).resolve()
      with tempfile.TemporaryDirectory() as td:
         tmp_root = Path(td)
         zip_path = tmp_root / 'restore.zip'
         uploaded.save(zip_path)
         ok, detail = _verify_backup_zip(zip_path)
         if not ok:
            raise ValueError('Backup non valido: ' + detail)
         with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
               if info.is_dir():
                  continue
               if not _is_safe_zip_member(info.filename):
                  raise ValueError(f'Percorso non ammesso nel backup: {info.filename}')
            zf.extractall(tmp_root / 'extract')

         extracted = tmp_root / 'extract'
         pre_restore = _create_backup_zip('pre_restore')

         candidates = [
            extracted / 'tenants' / tenant_slug / 'asd.db',
            extracted / 'database' / 'asd.db',
         ]
         source_db = next((x for x in candidates if x.exists() and x.is_file()), None)
         if source_db is None:
            raise ValueError(f'Backup senza database per tenant {tenant_slug}.')

         check_conn = sqlite3.connect(str(source_db))
         try:
            check = check_conn.execute('PRAGMA integrity_check').fetchone()
            if not check or str(check[0]).lower() != 'ok':
               raise ValueError(f'Database backup non integro: {check[0] if check else "nessun esito"}')
         finally:
            check_conn.close()

         target_db.parent.mkdir(parents=True, exist_ok=True)
         atomic_tmp = target_db.with_name(target_db.name + '.restore-tmp')
         shutil.copy2(source_db, atomic_tmp)
         verify_conn = sqlite3.connect(str(atomic_tmp))
         try:
            check2 = verify_conn.execute('PRAGMA integrity_check').fetchone()
            if not check2 or str(check2[0]).lower() != 'ok':
               raise ValueError('Copia temporanea DB restore non integra.')
         finally:
            verify_conn.close()
         _os.replace(str(atomic_tmp), str(target_db))

         cfg_candidates = [
            extracted / 'tenants' / tenant_slug / 'config.json',
            extracted / 'config' / 'config.json',
         ]
         src_cfg = next((x for x in cfg_candidates if x.exists() and x.is_file()), None)
         if src_cfg:
            target_cfg.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_cfg, target_cfg)

         for folder in ('media', 'pdf', 'user_static'):
            src = extracted / folder
            dst = DATA_DIR / folder
            if src.exists() and src.is_dir():
               if dst.exists():
                  shutil.rmtree(dst)
               shutil.copytree(src, dst)

         src_tenant = extracted / 'tenants' / tenant_slug
         if src_tenant.exists() and src_tenant.is_dir():
            for item in src_tenant.rglob('*'):
               if not item.is_file() or item.name == 'asd.db':
                  continue
               rel = item.relative_to(src_tenant)
               dst = get_tenant_root(tenant_slug) / rel
               dst.parent.mkdir(parents=True, exist_ok=True)
               shutil.copy2(item, dst)

      init_db_for_path(target_db, tenant_slug=tenant_slug)
      final_conn = sqlite3.connect(str(target_db))
      try:
         final_ok = final_conn.execute('PRAGMA integrity_check').fetchone()[0]
         final_count = final_conn.execute('SELECT COUNT(*) FROM tesserati').fetchone()[0]
      finally:
         final_conn.close()
      if str(final_ok).lower() != 'ok':
         raise RuntimeError('Restore completato ma integrity_check finale non OK.')
      log_audit('backup_restore', details=f'Backup ZIP ripristinato · tesserati={final_count} · pre_restore={pre_restore.name}', entity_type='backup')
      return redirect_with_message('/backup', f'Backup ripristinato correttamente. Tesserati: {final_count}. Backup sicurezza: {pre_restore.name}', 'success')
   except Exception as exc:
      try: log_exception(f"backup_restore: {exc}")
      except Exception: pass
      return redirect_with_message('/backup', f'Errore restore: {exc}', 'error')


@app.route('/backup/test', methods=['POST'])
@login_required
@admin_required
def backup_test_integrity():
   try:
      p=_create_backup_zip('backup_test')
      ok,detail=_verify_backup_zip(p)
      try: p.unlink(missing_ok=True)
      except Exception: pass
      return redirect_with_message('/backup', ('Backup verificato: '+detail) if ok else ('Backup NON valido: '+detail), 'success' if ok else 'error')
   except Exception as exc:
      return redirect_with_message('/backup', f'Test backup fallito: {exc}', 'error')
