pub fn add(a: i64, b: i64) -> i64 {
    a + b
}

pub fn subtract(a: i64, b: i64) -> i64 {
    a - b
}

pub fn multiply(a: i64, b: i64) -> i64 {
    a * b
}

pub fn divide(a: i64, b: i64) -> Result<f64, String> {
    if b == 0 {
        Err("Division by zero is not allowed".to_string())
    } else {
        Ok(a as f64 / b as f64)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn 正の数を足すと正しい結果が返る() {
        assert_eq!(add(2, 3), 5);
    }

    #[test]
    fn 負の数を足すと正しい結果が返る() {
        assert_eq!(add(-2, 3), 1);
    }

    #[test]
    fn 正の数を引くと正しい結果が返る() {
        assert_eq!(subtract(5, 3), 2);
    }

    #[test]
    fn 正の数をかけると正しい結果が返る() {
        assert_eq!(multiply(2, 3), 6);
    }

    #[test]
    fn 正の数で割ると正しい結果が返る() {
        assert_eq!(divide(6, 3).unwrap(), 2.0);
    }

    #[test]
    fn ゼロで割るとエラーが返る() {
        assert!(divide(5, 0).is_err());
    }
}
