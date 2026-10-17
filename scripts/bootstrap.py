"""Default Compose initialization: idempotent CSV import and semantic index."""
import subprocess
import sys


def main():
    subprocess.run([sys.executable,'-m','scripts.load_olist','--profile'],check=True)
    subprocess.run([sys.executable,'-m','scripts.index_knowledge'],check=True)


if __name__=='__main__':main()
