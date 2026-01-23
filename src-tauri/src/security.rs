use std::path::{Path, PathBuf};

/// Forbidden paths that should never be accessible
pub fn get_forbidden_paths() -> Vec<&'static str> {
    vec![
        "/System",
        "/Library",
        "/bin",
        "/sbin",
        "/usr/bin",
        "/usr/sbin",
        "C:\\Windows",
        "C:\\Program Files",
        "C:\\Program Files (x86)",
        ".ssh",
        ".env",
        ".aws",
        ".config",
    ]
}

/// Validate if a path is safe to access
pub fn validate_path(path: &Path, allowed_directories: &[PathBuf]) -> bool {
    // Resolve the path to get absolute path
    let resolved = match path.canonicalize() {
        Ok(p) => p,
        Err(_) => return false, // Path doesn't exist or can't be accessed
    };

    // Check against forbidden paths
    let path_str = resolved.to_string_lossy().to_lowercase();
    for forbidden in get_forbidden_paths() {
        let forbidden_lower = forbidden.to_lowercase();
        if path_str.contains(&forbidden_lower) {
            log::warn!("Blocked access to forbidden path: {:?}", resolved);
            return false;
        }
    }

    // Check if path is within allowed directories
    for allowed_dir in allowed_directories {
        let allowed_resolved = match allowed_dir.canonicalize() {
            Ok(p) => p,
            Err(_) => continue,
        };

        if resolved.starts_with(&allowed_resolved) {
            return true;
        }
    }

    log::warn!("Path not in allowed directories: {:?}", resolved);
    false
}

/// Check if a path is a system-critical directory
pub fn is_system_critical(path: &Path) -> bool {
    let critical_dirs = vec![
        "/",
        "/System",
        "/Library",
        "/bin",
        "/sbin",
        "C:\\",
        "C:\\Windows",
        "C:\\Program Files",
    ];

    let path_str = path.to_string_lossy();
    critical_dirs.iter().any(|&critical| path_str == critical)
}

/// Get the risk level of an operation on a path
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RiskLevel {
    Low,      // Read operations
    Medium,   // Move, rename
    High,     // Delete single file
    Critical, // Delete multiple files or directories
}

pub fn get_operation_risk_level(
    operation: &str,
    file_count: usize,
    is_directory: bool,
) -> RiskLevel {
    match operation.to_lowercase().as_str() {
        "read" | "list" | "search" => RiskLevel::Low,
        "move" | "rename" | "copy" => {
            if file_count > 10 {
                RiskLevel::High
            } else {
                RiskLevel::Medium
            }
        }
        "delete" | "remove" => {
            if is_directory || file_count > 5 {
                RiskLevel::Critical
            } else if file_count > 1 {
                RiskLevel::High
            } else {
                RiskLevel::Medium
            }
        }
        _ => RiskLevel::Medium,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_forbidden_paths() {
        let temp_dir = std::env::temp_dir();
        let allowed = vec![temp_dir.clone()];

        // Should be allowed
        assert!(validate_path(&temp_dir, &allowed));

        // System paths should be blocked (if they exist)
        #[cfg(unix)]
        {
            if Path::new("/bin").exists() {
                assert!(!validate_path(Path::new("/bin"), &allowed));
            }
        }
    }

    #[test]
    fn test_risk_levels() {
        assert_eq!(get_operation_risk_level("read", 1, false), RiskLevel::Low);
        assert_eq!(
            get_operation_risk_level("move", 5, false),
            RiskLevel::Medium
        );
        assert_eq!(get_operation_risk_level("delete", 10, false), RiskLevel::High);
        assert_eq!(
            get_operation_risk_level("delete", 1, true),
            RiskLevel::Critical
        );
    }
}