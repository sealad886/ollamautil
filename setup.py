from setuptools import setup, find_packages

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name='ollamautil',
    version='0.1.0',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    install_requires=[
        'prettytable',
        'tqdm',
        'ollama'
    ],
    entry_points={
        'console_scripts': [
            'ollamautil=ollamautil.cli:main',
        ],
    },
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/yourusername/ollamautil',
    author='Andrew Cox',
    author_email='your.email@example.com',
    license='GPL-3.0',
    description='A CLI utility for managing Ollama cache.',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Utilities',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
