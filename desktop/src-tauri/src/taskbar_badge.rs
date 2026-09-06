use tauri::image::Image;

const SIZE: usize = 32;
const SCALE: usize = 4;
const RASTER: usize = SIZE * SCALE;

fn badge_label(count: u32) -> String {
    if count > 99 {
        "99+".into()
    } else {
        count.to_string()
    }
}

/// Render the system typeface at 4x resolution, then downsample both the glyph
/// and circular silhouette. The shell can scale this cleanly at different DPIs.
pub fn unread_badge(count: u32) -> Result<Image<'static>, String> {
    let glyph = text_mask(&badge_label(count))?;
    let mut rgba = vec![0u8; SIZE * SIZE * 4];
    let center = RASTER as f64 / 2.0;
    let radius = center - SCALE as f64;
    let color = [38u32, 111, 166];
    for y in 0..SIZE {
        for x in 0..SIZE {
            let mut coverage = 0u32;
            let mut channels = [0u32; 3];
            for sy in 0..SCALE {
                for sx in 0..SCALE {
                    let px = x * SCALE + sx;
                    let py = y * SCALE + sy;
                    if (px as f64 + 0.5 - center).powi(2) + (py as f64 + 0.5 - center).powi(2)
                        > radius * radius
                    {
                        continue;
                    }
                    coverage += 1;
                    let ink = glyph[py * RASTER + px] as u32;
                    for channel in 0..3 {
                        channels[channel] += color[channel] + (255 - color[channel]) * ink / 255;
                    }
                }
            }
            if coverage > 0 {
                let offset = (y * SIZE + x) * 4;
                for channel in 0..3 {
                    rgba[offset + channel] = (channels[channel] / coverage) as u8;
                }
                rgba[offset + 3] = (coverage * 255 / (SCALE * SCALE) as u32) as u8;
            }
        }
    }
    Ok(Image::new_owned(rgba, SIZE as u32, SIZE as u32))
}

#[cfg(windows)]
fn text_mask(label: &str) -> Result<Vec<u8>, String> {
    use windows::core::w;
    use windows::Win32::Foundation::{COLORREF, RECT};
    use windows::Win32::Graphics::Gdi::*;

    struct Surface {
        dc: HDC,
        bitmap: HBITMAP,
        font: HFONT,
    }
    impl Drop for Surface {
        fn drop(&mut self) {
            unsafe {
                // Release selections before deleting the owned GDI objects.
                let _ = DeleteDC(self.dc);
                let _ = DeleteObject(self.font.into());
                let _ = DeleteObject(self.bitmap.into());
            }
        }
    }
    unsafe {
        let mut surface = Surface {
            dc: CreateCompatibleDC(None),
            bitmap: HBITMAP::default(),
            font: HFONT::default(),
        };
        if surface.dc.is_invalid() {
            return Err("Cannot create badge text surface".into());
        }
        let info = BITMAPINFO {
            bmiHeader: BITMAPINFOHEADER {
                biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
                biWidth: RASTER as i32,
                biHeight: -(RASTER as i32),
                biPlanes: 1,
                biBitCount: 32,
                biCompression: BI_RGB.0,
                ..Default::default()
            },
            ..Default::default()
        };
        let mut bits = std::ptr::null_mut();
        surface.bitmap =
            CreateDIBSection(Some(surface.dc), &info, DIB_RGB_COLORS, &mut bits, None, 0)
                .map_err(|error| error.to_string())?;
        if bits.is_null() {
            return Err("Cannot allocate badge bitmap".into());
        }
        let pixels = std::slice::from_raw_parts_mut(bits as *mut u8, RASTER * RASTER * 4);
        pixels.fill(0);
        SelectObject(surface.dc, surface.bitmap.into());
        let height = match label.len() {
            1 => 88,
            2 => 78,
            _ => 61,
        };
        surface.font = CreateFontW(
            -height,
            0,
            0,
            0,
            600,
            0,
            0,
            0,
            DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS,
            CLIP_DEFAULT_PRECIS,
            ANTIALIASED_QUALITY,
            0,
            w!("Segoe UI"),
        );
        if surface.font.is_invalid() {
            return Err("Cannot create badge typeface".into());
        }
        SelectObject(surface.dc, surface.font.into());
        SetBkMode(surface.dc, TRANSPARENT);
        SetTextColor(surface.dc, COLORREF(0x00ff_ffff));
        let mut text: Vec<u16> = label.encode_utf16().collect();
        let mut rect = RECT {
            left: 0,
            top: 0,
            right: RASTER as i32,
            bottom: RASTER as i32,
        };
        if DrawTextW(
            surface.dc,
            &mut text,
            &mut rect,
            DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX,
        ) == 0
        {
            return Err("Cannot draw badge text".into());
        }
        let _ = GdiFlush();
        Ok(pixels.chunks_exact(4).map(|pixel| pixel[0]).collect())
    }
}

#[cfg(not(windows))]
fn text_mask(_label: &str) -> Result<Vec<u8>, String> {
    // Only Windows uses taskbar overlay icons.
    Ok(vec![0; RASTER * RASTER])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn badge_has_symmetric_antialiased_edges_and_transparent_corners() {
        for count in [1, 8, 12, 99, 100, u32::MAX] {
            let badge = unread_badge(count).unwrap();
            let pixels = badge.rgba();
            // Optional native-render evidence without opening the app or a toast.
            if let Ok(directory) = std::env::var("SMARTI_BADGE_PREVIEW_DIR") {
                let directory = std::path::Path::new(&directory);
                std::fs::create_dir_all(directory).unwrap();
                std::fs::write(directory.join(format!("badge-{count}.rgba")), pixels).unwrap();
            }
            assert_eq!(pixels[3], 0);
            assert!(pixels.chunks_exact(4).any(|p| p[3] > 0 && p[3] < 255));
            for y in 0..SIZE {
                for x in 0..SIZE {
                    assert_eq!(
                        pixels[(y * SIZE + x) * 4 + 3],
                        pixels[(y * SIZE + SIZE - 1 - x) * 4 + 3]
                    );
                }
            }
            #[cfg(windows)]
            assert!(pixels
                .chunks_exact(4)
                .any(|p| p[0] > 230 && p[1] > 230 && p[3] == 255));
        }
        assert_eq!(badge_label(100), "99+");
    }
}
