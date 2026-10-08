//! Kernel ownership of the desktop's Core, including an abrupt desktop exit.
//! The handle is private/non-inheritable and never assigned to an existing app.
use std::process::Child;

#[cfg(windows)]
pub struct CoreProcessJob(windows::Win32::Foundation::HANDLE);
#[cfg(windows)]
unsafe impl Send for CoreProcessJob {}
#[cfg(windows)]
unsafe impl Sync for CoreProcessJob {}

#[cfg(windows)]
impl CoreProcessJob {
    pub fn new() -> Result<Self, String> {
        use windows::Win32::System::JobObjects::{CreateJobObjectW, SetInformationJobObject, JobObjectExtendedLimitInformation, JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, JOB_OBJECT_LIMIT_BREAKAWAY_OK};
        let job = Self(unsafe { CreateJobObjectW(None, None) }.map_err(|error| error.to_string())?);
        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK;
        unsafe { SetInformationJobObject(job.0, JobObjectExtendedLimitInformation, (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(), std::mem::size_of_val(&limits) as u32) }.map_err(|error| error.to_string())?;
        Ok(job)
    }

    pub fn attach(&self, child: &Child) -> Result<(), String> {
        use std::os::windows::io::AsRawHandle;
        use windows::Win32::{Foundation::HANDLE, System::JobObjects::AssignProcessToJobObject};
        unsafe { AssignProcessToJobObject(self.0, HANDLE(child.as_raw_handle())) }.map_err(|error| format!("Cannot bind Core to its desktop owner: {error}"))
    }
}

#[cfg(windows)]
impl Drop for CoreProcessJob {
    fn drop(&mut self) { let _ = unsafe { windows::Win32::Foundation::CloseHandle(self.0) }; }
}

#[cfg(not(windows))]
pub struct CoreProcessJob;
#[cfg(not(windows))]
impl CoreProcessJob {
    pub fn new() -> Result<Self, String> { Ok(Self) }
    pub fn attach(&self, _child: &Child) -> Result<(), String> { Ok(()) }
}
