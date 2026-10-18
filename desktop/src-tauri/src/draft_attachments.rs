use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

const MAX_BYTES: u64 = 25 * 1024 * 1024;

pub fn stage(root: &Path, name: &str, bytes: &[u8]) -> Result<PathBuf, String> {
    if bytes.is_empty() || bytes.len() as u64 > MAX_BYTES {
        return Err("Attachment must be between 1 byte and 25 MB".into());
    }
    fs::create_dir_all(root).map_err(|error| error.to_string())?;
    let name: String = name.chars().map(|c| if c.is_alphanumeric() || matches!(c, '.' | '-' | '_') { c } else { '_' }).take(120).collect();
    let path = root.join(format!("{}-{}", crate::launch_token(), if name.is_empty() { "attachment" } else { &name }));
    let mut file = OpenOptions::new().write(true).create_new(true).open(&path).map_err(|error| error.to_string())?;
    file.write_all(bytes).and_then(|_| file.sync_all()).map_err(|error| error.to_string())?;
    Ok(path)
}

pub fn allowed(path: &Path, roots: &[PathBuf]) -> Result<PathBuf, String> {
    let target = fs::canonicalize(path).map_err(|_| "Attachment was not found".to_string())?;
    if !roots.iter().filter_map(|root| fs::canonicalize(root).ok()).any(|root| target.starts_with(root)) {
        return Err("Attachment is outside the managed storage".into());
    }
    let metadata = fs::metadata(&target).map_err(|error| error.to_string())?;
    if !metadata.is_file() || metadata.len() == 0 || metadata.len() > MAX_BYTES {
        return Err("Attachment is not an allowed file".into());
    }
    Ok(target)
}

pub fn retain(path: &Path, root: &Path, legacy: &Path) -> Result<PathBuf, String> {
    let target = allowed(path, &[root.to_path_buf(), legacy.to_path_buf()])?;
    if fs::canonicalize(root).is_ok_and(|root| target.starts_with(root)) { return Ok(target); }
    let bytes = fs::read(&target).map_err(|error| error.to_string())?;
    stage(root, target.file_name().and_then(|name| name.to_str()).unwrap_or("attachment"), &bytes)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn durable_files_reopen_and_legacy_copy_never_removes_the_source() {
        let base = std::env::temp_dir().join(format!("smarti-draft-test-{}", crate::launch_token()));
        let root = base.join("durable"); let legacy = base.join("cache");
        let old = stage(&legacy, "תמונה.png", b"image bytes").unwrap();
        let retained = retain(&old, &root, &legacy).unwrap();
        assert_eq!(fs::read(allowed(&retained, &[root.clone()]).unwrap()).unwrap(), b"image bytes");
        assert!(old.exists());
        assert_eq!(retain(&retained, &root, &legacy).unwrap(), fs::canonicalize(retained).unwrap());
        assert!(stage(&root, "empty", b"").is_err());
        assert!(allowed(&base, &[root.clone()]).is_err());
        assert!(retain(&old, &root, &base.join("other")).is_err());
        // Only this test's explicitly created, verified temporary directory.
        assert!(base.starts_with(std::env::temp_dir()));
        fs::remove_dir_all(base).unwrap();
    }
}
